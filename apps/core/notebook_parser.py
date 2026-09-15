"""
Standalone Jupyter notebook (.ipynb) parser — pure stdlib, no Django dependency.

Serves as the single source of truth for understanding notebook materials
(ClassLib/*.ipynb) across the project:

1. Claude Code skill ``.claude/skills/notebook-reader`` runs it via CLI to get
   an AI-friendly digest of a notebook before generating 教案 / lessons / exercises.
2. Management commands ``import_notebook`` / ``load_notebook_data`` use it to
   extract cells, sections and code outputs for the database.

Conventions understood by this parser (see the skill for details):
- Chapter headings: ``# 第X章 ...`` or ``<h1>第X章</h1>`` (Chinese numerals OK)
- Lesson/section headings: ``X.Y 标题`` (e.g. ``## 1.1 数字常量``)
- Subsection headings: ``X.Y.Z`` (e.g. ``### 1.5.1 ...``) — stay inside a lesson
- Noise cells are *flagged*, not dropped: LaTeX symbol tables, pasted
  extension README pages, ``!pip install`` setup cells, TOC/back-link cells,
  and a stray ``###`` line left at the top of some code cells.

CLI:
    python apps/core/notebook_parser.py <file.ipynb>
        [--format digest|json|sections|cells]
        [--max-output N]        # truncate per-cell output text (default 2000)
        [--include-noise]       # keep noise cells in cells/sections output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

_CHAPTER_RE = re.compile(r"^第\s*[0-9一二三四五六七八九十百]+\s*章")
_SECTION_RE = re.compile(r"^(\d+)\.(\d+)\s+(.+)")
_SUBSECTION_RE = re.compile(r"^\d+\.\d+\.\d+")
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_HTML_HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MATH_BLOCK_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_MATH_INLINE_RE = re.compile(r"\$[^$\n]+\$")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(#[^)]*\)")
_README_NOISE_RE = re.compile(
    r"Project Details|Publisher|Download Extension|Works with|Released on"
    r"|Report Abuse|Last Commit|No Pull Requests|Open Issues|Repository"
    r"|Homepage|License|Changelog|Categories|Tags|keybindings"
)
_STRIP_CODE_ARTIFACT_RE = re.compile(r"^\s*#{1,6}\s*$")

_CJK_RE = re.compile(r"[一-鿿]")


def _join_source(source) -> str:
    if isinstance(source, list):
        return "".join(source)
    return source or ""


def _strip_code_artifact(source: str) -> str:
    """Drop stray bare-``###`` lines left at the top of some code cells."""
    lines = source.split("\n")
    while lines and _STRIP_CODE_ARTIFACT_RE.match(lines[0]):
        lines.pop(0)
    return "\n".join(lines)


def _math_stripped(text: str) -> str:
    """Text with $$...$$ blocks and $...$ spans removed (for noise sniffing)."""
    text = _MATH_BLOCK_RE.sub(" ", text)
    text = _MATH_INLINE_RE.sub(" ", text)
    return text


def _alnum_count(text: str) -> int:
    return sum(c.isalnum() for c in text)


def _extract_output(outputs: list, max_chars: int) -> tuple[str, str]:
    """Return (output_text, error_text) from a code cell's outputs."""
    out_parts: list[str] = []
    err_parts: list[str] = []
    total = 0
    for output in outputs or []:
        if output.get("output_type") == "stream":
            text = _join_source(output.get("text"))
            if output.get("name") == "stderr":
                err_parts.append(text)
            else:
                out_parts.append(text)
        elif output.get("output_type") == "error":
            err_parts.append(
                f"{output.get('ename', 'Error')}: {output.get('evalue', '')}"
            )
        elif "data" in output and "text/plain" in output["data"]:
            out_parts.append(_join_source(output["data"]["text/plain"]))
        if out_parts or err_parts:
            total = sum(len(p) for p in out_parts) + sum(len(p) for p in err_parts)
            if total >= max_chars:
                break
    output_text = "\n".join(p for p in out_parts if p.strip())
    error_text = "\n".join(p for p in err_parts if p.strip())
    if len(output_text) > max_chars:
        output_text = output_text[:max_chars] + "\n…(输出已截断)"
    return output_text, error_text


def _classify_noise(source: str) -> dict[str, bool]:
    """Flag cell types that should be skipped when generating content."""
    residual = _math_stripped(source)
    stripped = _HTML_TAG_RE.sub(" ", residual)
    stripped = _MD_LINK_RE.sub(" ", stripped).strip()
    cjk = len(_CJK_RE.findall(stripped))
    flags = {
        "is_symbol_table": bool(re.search(_MATH_INLINE_RE, source) or _MATH_BLOCK_RE.search(source))
        and cjk < 10
        and _alnum_count(stripped) < 40,
        "is_readme_noise": len(_README_NOISE_RE.findall(source)) >= 3,
        "is_toc": len(_MD_LINK_RE.findall(source)) >= 3 or (bool(_MD_LINK_RE.search(source)) and not stripped),
        "is_setup": False,
        # truly empty, or a stray bare-``###`` marker cell
        "is_empty": not source.strip()
        or bool(_STRIP_CODE_ARTIFACT_RE.match(source.strip())),
    }
    return flags


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class CellItem:
    index: int
    cell_type: str
    source: str
    output: str = ""
    error: str = ""
    execution_count: int = 0
    headings: list[tuple[int, str]] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)

    @property
    def first_heading(self) -> tuple[int, str] | None:
        return self.headings[0] if self.headings else None

    @property
    def is_noise(self) -> bool:
        return any(
            self.flags.get(k)
            for k in ("is_symbol_table", "is_readme_noise", "is_toc", "is_setup", "is_empty")
        )

    def to_dict(self, max_output: int | None = None) -> dict:
        output = self.output
        if max_output is not None and len(output) > max_output:
            output = output[:max_output] + "\n…(输出已截断)"
        return {
            "index": self.index,
            "cell_type": self.cell_type,
            "source": self.source,
            "output": output,
            "error": self.error,
            "execution_count": self.execution_count,
            "headings": [{"level": l, "text": t} for l, t in self.headings],
            "flags": self.flags,
        }


@dataclass
class Section:
    number: str  # "1.1" or "" for intro sections
    title: str
    cells: list[CellItem] = field(default_factory=list)
    chapter: str = ""

    @property
    def label(self) -> str:
        return f"{self.number} {self.title}".strip() if self.number else self.title

    @property
    def cell_range(self) -> tuple[int, int] | None:
        if not self.cells:
            return None
        return self.cells[0].index, self.cells[-1].index

    def stats(self) -> dict[str, int]:
        md = sum(1 for c in self.cells if c.cell_type == "markdown")
        code = sum(1 for c in self.cells if c.cell_type == "code")
        return {"markdown": md, "code": code, "total": len(self.cells)}


@dataclass
class NotebookDoc:
    path: str
    nbformat: str = ""
    title: str = ""
    chapters: list[str] = field(default_factory=list)
    cells: list[CellItem] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)

    def __post_init__(self):
        if not self.title:
            self.title = Path(self.path).stem

    # -- derived views -------------------------------------------------------

    def stats(self) -> dict[str, int]:
        md = sum(1 for c in self.cells if c.cell_type == "markdown")
        code = sum(1 for c in self.cells if c.cell_type == "code")
        return {
            "total": len(self.cells),
            "markdown": md,
            "code": code,
            "with_output": sum(1 for c in self.cells if c.output),
            "noise": sum(1 for c in self.cells if c.is_noise),
        }

    def noise_cells(self) -> list[CellItem]:
        return [c for c in self.cells if c.is_noise]

    def to_digest(self, max_output: int = 2000) -> str:
        """Compact structural digest for AI consumption."""
        s = self.stats()
        lines = [
            f"# {self.title} — 结构摘要",
            f"nbformat {self.nbformat} | 共 {s['total']} 个单元格 "
            f"({s['markdown']} 文本, {s['code']} 代码, {s['with_output']} 个有输出)",
            "",
        ]
        if self.chapters:
            lines.append(f"章节: {', '.join(self.chapters)}")
            lines.append("")
        lines.append("## 内容结构")
        for sec in self.sections:
            stats = sec.stats()
            rng = sec.cell_range
            rng_txt = f"单元格 {rng[0]}-{rng[1]}" if rng else "无内容"
            lines.append(
                f"- **{sec.label}** | {rng_txt} | {stats['markdown']} 文本, {stats['code']} 代码"
            )
            summary = self._section_summary(sec)
            if summary:
                lines.append(f"    要点: {summary}")
        lines.append("")
        noise = self.noise_cells()
        if noise:
            lines.append("## 噪音/跳过提示（生成教案或课程内容时跳过）")
            lines.extend(f"- 单元格 {c.index}: {self._noise_reason(c)}" for c in noise)
            lines.append("")
        lines.append(
            "提示: 使用 --format json 查看任意单元格的完整内容；"
            "代码单元格的 output 字段是可信的执行结果，可用作习题答案的基准。"
        )
        return "\n".join(lines)

    def _section_summary(self, sec: Section, limit: int = 120) -> str:
        for c in sec.cells:
            if c.cell_type != "markdown" or c.is_noise:
                continue
            text = _HTML_TAG_RE.sub(" ", c.source)
            text = _MATH_INLINE_RE.sub(" ", text)
            # drop heading lines — the section label already carries the title
            text = re.sub(r"(?m)^\s*#{1,6}\s+.*$", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 6:  # skip pure heading cells
                return text[:limit] + ("…" if len(text) > limit else "")
        return ""

    @staticmethod
    def _noise_reason(c: CellItem) -> str:
        if c.flags.get("is_symbol_table"):
            return "LaTeX 符号表"
        if c.flags.get("is_readme_noise"):
            return "粘贴的插件 README 页面"
        if c.flags.get("is_toc"):
            return "目录/跳转链接"
        if c.flags.get("is_setup"):
            return "环境安装命令 (!pip)"
        if c.flags.get("is_empty"):
            return "空单元格"
        return "噪音"

    def to_cell_payloads(self, include_noise: bool = True) -> list[dict]:
        """Cells in the learning app's ``Cell`` data format.

        {'cell_type': 'text', 'data': {'markdown': ...}} or
        {'cell_type': 'code', 'data': {'source': ..., 'output': ...}}.
        """
        payloads = []
        for c in self.cells:
            if not include_noise and c.is_noise:
                continue
            payload = cell_payload(c)
            if payload:
                payloads.append(payload)
        return payloads

    def to_json(self, max_output: int = 2000) -> dict:
        return {
            "path": self.path,
            "title": self.title,
            "nbformat": self.nbformat,
            "chapters": self.chapters,
            "stats": self.stats(),
            "sections": [
                {
                    "number": sec.number,
                    "title": sec.title,
                    "chapter": sec.chapter,
                    "cell_range": list(sec.cell_range) if sec.cell_range else None,
                    "cells": [c.to_dict(max_output) for c in sec.cells],
                }
                for sec in self.sections
            ],
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _cell_headings(cell: dict) -> list[tuple[int, str]]:
    """Collect markdown / HTML headings in one cell, in source order."""
    headings: list[tuple[int, str]] = []
    if cell.get("cell_type") != "markdown":
        return headings
    text = _join_source(cell.get("source"))
    lines = text.split("\n")
    for line in lines:
        m = _MD_HEADING_RE.match(line.strip())
        if m:
            headings.append((len(m.group(1)), m.group(2).strip()))
        else:
            for hm in _HTML_HEADING_RE.finditer(line):
                headings.append((int(hm.group(1)), _HTML_TAG_RE.sub("", hm.group(2)).strip()))
    return headings


def cell_payload(c: CellItem) -> dict | None:
    """Map one parsed cell to the learning app's ``Cell`` data format.

    Returns None for cells that should never be imported (empty/stray
    marker cells). Noise cells are the caller's choice via ``include_noise``.
    """
    if c.flags.get("is_empty"):
        return None
    if c.cell_type == "markdown":
        return {"cell_type": "text", "data": {"markdown": c.source}}
    if c.cell_type == "code":
        return {
            "cell_type": "code",
            "data": {
                "source": c.source,
                "output": c.output,
                "execution_count": c.execution_count or 0,
                "status": "success" if c.output and not c.error else "pending",
            },
        }
    return None


def parse_notebook(path: str | Path, max_output: int = 2000) -> NotebookDoc:
    """Parse an .ipynb file into a :class:`NotebookDoc`."""
    path = str(path)
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if "cells" not in raw:
        raise ValueError(f"{path}: not a valid .ipynb file (missing 'cells')")

    doc = NotebookDoc(
        path=path,
        nbformat=f"{raw.get('nbformat', '')}.{raw.get('nbformat_minor', '')}",
    )
    for i, cell in enumerate(raw.get("cells", [])):
        cell_type = cell.get("cell_type", "markdown")
        source = _join_source(cell.get("source"))
        output, error = ("", "")
        if cell_type == "code":
            source = _strip_code_artifact(source)
            output, error = _extract_output(cell.get("outputs", []), max_output)
        flags = _classify_noise(source)
        if cell_type == "code" and source.lstrip().startswith("!"):
            flags["is_setup"] = True
        doc.cells.append(
            CellItem(
                index=i,
                cell_type=cell_type,
                source=source,
                output=output,
                error=error,
                execution_count=cell.get("execution_count") or 0,
                headings=_cell_headings(cell),
                flags=flags,
            )
        )

    doc.chapters, doc.sections = _build_structure(doc.cells)
    for cell in doc.cells:
        if cell.first_heading and _CHAPTER_RE.match(cell.first_heading[1]):
            doc.title = cell.first_heading[1].strip()
            break
    return doc


def _build_structure(
    cells: list[CellItem],
) -> tuple[list[str], list[Section]]:
    """Split cells into chapters and lesson-level sections.

    A chapter heading starts a new chapter AND a new intro section; a
    ``X.Y`` heading starts a new lesson section; ``X.Y.Z`` headings stay
    inside the current lesson.
    """
    chapters: list[str] = []
    sections: list[Section] = []
    current_chapter = ""
    current: Section | None = None

    def start_section(number: str, title: str):
        nonlocal current
        current = Section(number=number, title=title, chapter=current_chapter)
        sections.append(current)

    start_section("", "导论")
    for cell in cells:
        heading = cell.first_heading
        if heading:
            level, text = heading
            if _CHAPTER_RE.match(text):
                chapter_title = text.strip()
                if chapter_title not in chapters:
                    chapters.append(chapter_title)
                current_chapter = chapter_title
                # a chapter heading opens a new intro section (cells before
                # the first X.Y heading belong to the chapter intro)
                start_section("", "导论")
            elif _SECTION_RE.match(text) and not _SUBSECTION_RE.match(text):
                m = _SECTION_RE.match(text)
                start_section(f"{m.group(1)}.{m.group(2)}", m.group(3).strip())
        assert current is not None
        current.cells.append(cell)

    # Drop trailing empty sections
    sections = [s for s in sections if s.cells]
    return chapters, sections


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a legacy ANSI codepage (e.g. GBK) for
    # piped stdout; force UTF-8 so Chinese content survives the pipe.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(
        description="Parse a Jupyter notebook for AI/content-generation use."
    )
    parser.add_argument("file", help="path to the .ipynb file")
    parser.add_argument(
        "--format",
        choices=["digest", "json", "sections", "cells"],
        default="digest",
        help="output format (default: digest)",
    )
    parser.add_argument(
        "--max-output", type=int, default=2000, help="truncate code output at N chars"
    )
    parser.add_argument(
        "--include-noise",
        action="store_true",
        help="include noise cells in cells/sections output",
    )
    args = parser.parse_args(argv)

    try:
        doc = parse_notebook(args.file, max_output=args.max_output)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"解析失败: {e}", file=sys.stderr)
        return 1

    if args.format == "digest":
        print(doc.to_digest(max_output=args.max_output))
    elif args.format == "json":
        print(json.dumps(doc.to_json(args.max_output), ensure_ascii=False, indent=2))
    elif args.format == "sections":
        print(
            json.dumps(
                [
                    {
                        "chapter": s.chapter,
                        "number": s.number,
                        "title": s.title,
                        "cell_range": list(s.cell_range) if s.cell_range else None,
                        "stats": s.stats(),
                        "cells": [c.to_dict(args.max_output) for c in s.cells],
                    }
                    for s in doc.sections
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.format == "cells":
        print(
            json.dumps(
                doc.to_cell_payloads(include_noise=args.include_noise),
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
