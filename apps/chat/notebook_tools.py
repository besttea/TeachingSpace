"""
Tool definitions that let the project's AI (chat assistant, and future
agents) use the notebook-reader capability: listing ClassLib materials,
reading a notebook's structure, or fetching one section's content.

These are the in-app counterpart of the Claude Code skill
``.claude/skills/notebook-reader``: both sit on top of the shared parser
``apps.core.notebook_parser``.

Safety model: tools are fixed server-side functions. The model only picks a
tool name + arguments from the schemas in ``TOOL_SCHEMAS``; execution stays
in our code with:

- filename whitelisting (must be an actual file inside ClassLib — no path
  traversal, no arbitrary files),
- size-capped results,
- noise cells (symbol tables, README pages, !pip cells, TOC links) excluded.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

from django.conf import settings

from apps.core.notebook_parser import NotebookDoc, parse_notebook

#: Max chars of tool result content handed back to the model.
MAX_RESULT_CHARS = 8000
#: Max chars of a single cell's source inside a section result.
MAX_CELL_CHARS = 1500

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "list_notebooks",
        "description": (
            "列出可用的教学资料（ClassLib 目录中的 notebook），包含每本的章节与各小节"
            "（如 1.1 数字常量）的结构概览。当学生问'有什么资料/课程'或不确定该查哪"
            "一本 notebook 时，先调用此工具。"
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_notebook_digest",
        "description": (
            "查看指定 notebook 的结构摘要：章节、各小节标题与要点、单元格统计、噪音提示。"
            "回答'这门课讲什么/包含哪些内容'类问题时调用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "notebook 文件名，例如 第一课_基本数据结构.ipynb（先用 list_notebooks 获取准确文件名）",
                }
            },
            "required": ["filename"],
        },
    },
    {
        "name": "get_notebook_section",
        "description": (
            "读取指定 notebook 中某一节的完整内容：文本讲解、代码单元格及其历史执行输出。"
            "回答具体知识点问题（如'1.2 节讲了哪些数据类型'、'这个例子的运行结果是什么'）"
            "时必须先调用此工具，基于返回的真实内容回答，不要凭记忆编造。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "notebook 文件名，例如 第一课_基本数据结构.ipynb",
                },
                "section": {
                    "type": "string",
                    "description": "节编号或标题，例如 '1.2' 或 '标准数据类型'；'导论' 表示正式小节之前的内容",
                },
            },
            "required": ["filename", "section"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------


def _classlib_dir() -> str:
    return os.path.join(settings.BASE_DIR, "ClassLib")


def _resolve_notebook(filename: str) -> Optional[str]:
    """Whitelist-resolve a notebook name inside ClassLib.

    Rejects anything that is not exactly the basename of an existing .ipynb
    file in ClassLib (blocks ``../`` traversal and arbitrary file reads).
    """
    if not filename or os.path.basename(filename) != filename:
        return None
    path = os.path.join(_classlib_dir(), filename)
    if not (filename.endswith(".ipynb") and os.path.isfile(path)):
        return None
    return path


def _section_error(doc: NotebookDoc, section: str) -> Dict[str, Any]:
    return {
        "error": f"未找到节 '{section}'",
        "available_sections": [s.label for s in doc.sections],
    }


def list_notebooks() -> Dict[str, Any]:
    """List ClassLib notebooks with a per-notebook section overview."""
    classlib_dir = _classlib_dir()
    notebooks = []
    if os.path.isdir(classlib_dir):
        for filename in sorted(os.listdir(classlib_dir)):
            if not filename.endswith(".ipynb"):
                continue
            try:
                doc = parse_notebook(os.path.join(classlib_dir, filename))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            notebooks.append(
                {
                    "filename": filename,
                    "title": doc.title,
                    "stats": doc.stats(),
                    "sections": [s.label for s in doc.sections],
                }
            )
    return {"notebooks": notebooks}


def get_notebook_digest(filename: str) -> Dict[str, Any]:
    path = _resolve_notebook(filename)
    if path is None:
        return {"error": f"找不到 notebook：{filename}（先用 list_notebooks 查询可用的文件名）"}
    doc = parse_notebook(path)
    digest = doc.to_digest()
    return {"digest": digest[:MAX_RESULT_CHARS]}


def _section_content(doc: NotebookDoc, section: str) -> Optional[str]:
    """Render one section's cells (source + output) as compact text."""
    target = None
    for s in doc.sections:
        if s.number == section or s.title == section or s.label == section:
            target = s
            break
    if target is None:
        # allow loose title matching, e.g. section="标准数据类型" for "1.2 标准数据类型"
        for s in doc.sections:
            if section and (section in s.title or section in s.label):
                target = s
                break
    if target is None:
        return None

    parts = [f"节：{target.label}（共 {len(target.cells)} 个单元格）"]
    for cell in target.cells:
        if cell.is_noise:
            continue
        kind = "代码" if cell.cell_type == "code" else "讲解"
        header = f"[单元格 {cell.index} | {kind}"
        if cell.cell_type == "code" and cell.execution_count:
            header += f" | 执行次数 {cell.execution_count}"
        header += "]"
        body = cell.source[:MAX_CELL_CHARS]
        if cell.cell_type == "code" and cell.output:
            body += f"\n输出:\n{cell.output[:MAX_CELL_CHARS]}"
        if cell.cell_type == "code" and cell.error:
            body += f"\n报错:\n{cell.error[:MAX_CELL_CHARS]}"
        parts.append(f"{header}\n{body}")
    return "\n\n".join(parts)


def get_notebook_section(filename: str, section: str) -> Dict[str, Any]:
    path = _resolve_notebook(filename)
    if path is None:
        return {"error": f"找不到 notebook：{filename}（先用 list_notebooks 查询可用的文件名）"}
    doc = parse_notebook(path)
    content = _section_content(doc, section)
    if content is None:
        return _section_error(doc, section)
    return {"section": content[:MAX_RESULT_CHARS]}


def find_related_sections(query: str, max_sections: int = 3,
                          max_chars: int = MAX_RESULT_CHARS) -> str:
    """Scan ClassLib notebooks for sections related to ``query``.

    Used to auto-ground AI course generation in existing teaching material:
    returns the combined content of the best-matching sections ('' when
    nothing matches). Matching is a simple title/text overlap — good enough
    for Chinese teaching topics; deterministic and free.
    """
    if not query:
        return ''

    classlib_dir = _classlib_dir()
    if not os.path.isdir(classlib_dir):
        return ''

    tokens = [t for t in re.split(r'[\s，,、。;；:：/\\|]+', query) if len(t) >= 2]
    candidates = []  # (score, label, content)

    for filename in sorted(os.listdir(classlib_dir)):
        if not filename.endswith('.ipynb'):
            continue
        try:
            doc = parse_notebook(os.path.join(classlib_dir, filename))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for section in doc.sections:
            if section.number == '':  # intro sections carry no topic
                continue
            score = 0
            if query in section.label or section.label in query:
                score += 5
            for token in tokens:
                if token in section.title:
                    score += 3
                elif section.title in token:
                    score += 2
            if score <= 0:
                continue
            content = _section_content(doc, section.number) or ''
            candidates.append((score, f'{filename} · {section.label}', content))

    candidates.sort(key=lambda item: item[0], reverse=True)
    picked = candidates[:max_sections]
    if not picked:
        return ''

    parts = []
    for _score, label, content in picked:
        parts.append(f'【素材：{label}】\n{content}')
    return ('\n\n'.join(parts))[:max_chars]


TOOL_EXECUTORS = {
    "list_notebooks": list_notebooks,
    "get_notebook_digest": get_notebook_digest,
    "get_notebook_section": get_notebook_section,
}


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a tool call coming from the model. Unknown tools → error."""
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return {"error": f"未知工具：{name}"}
    try:
        return executor(**arguments)
    except TypeError:
        return {"error": f"工具 {name} 的参数有误：{arguments}"}
