"""Validate (AI-generated) Manim scripts before rendering.

Security + sanity checks. Manim rendering runs in a subprocess, but scripts
must not touch the filesystem/network beyond what Manim needs, so imports
and calls are restricted here. Rendering still runs with a timeout in
``manim_engine``.
"""

import ast

#: Hard cap on script size.
MAX_SCRIPT_CHARS = 50_000

#: Module roots that a Manim script has no reason to import.
FORBIDDEN_IMPORTS = {
    'os', 'sys', 'subprocess', 'socket', 'pathlib', 'shutil', 'requests',
    'urllib', 'http', 'ctypes', 'pickle', 'importlib', 'signal', 'pty',
}

#: Dangerous builtins/calls.
FORBIDDEN_CALLS = {'open', 'eval', 'exec', 'compile', '__import__', 'input'}


def validate_script(source: str) -> list[str]:
    """Return a list of problems (empty list == script is OK to render)."""
    problems: list[str] = []

    if len(source) > MAX_SCRIPT_CHARS:
        problems.append(f'脚本过长（{len(source)} 字符，上限 {MAX_SCRIPT_CHARS}）')

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f'语法错误: {e.msg}（第 {e.lineno} 行）']

    imports: set[str] = set()
    calls: set[str] = set()
    has_scene = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or '').split('.')[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == 'Scene':
                    has_scene = True

    problems.extend(f'禁止的 import: {m}' for m in sorted(imports & FORBIDDEN_IMPORTS))
    problems.extend(f'禁止的调用: {c}()' for c in sorted(calls & FORBIDDEN_CALLS))
    if not has_scene:
        problems.append('未定义继承自 Scene 的类')
    if 'manim' not in imports and not any('manim' in m for m in imports):
        problems.append('未导入 manim')

    return problems
