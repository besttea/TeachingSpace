"""Render Manim scripts to video via the Manim CLI (subprocess + timeout).

Rendering is slow and resource-heavy, so it always runs in a subprocess with
a hard timeout. The output file is copied out of Manim's directory layout
into MANIM_OUTPUT_DIR (default: media/videos/).
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from django.conf import settings

#: Manim quality flags (see `manim --help`).
QUALITY_FLAGS = {'low': '-ql', 'medium': '-qm', 'high': '-qh', 'production': '-qp'}

#: Default render timeout (seconds) — Manim scenes can be slow.
DEFAULT_TIMEOUT = 300


def _output_dir() -> Path:
    configured = getattr(settings, 'MANIM_OUTPUT_DIR', '')
    base = Path(configured) if configured else Path(settings.BASE_DIR) / 'media' / 'videos'
    base.mkdir(parents=True, exist_ok=True)
    return base


def _find_rendered_video(out_root: Path, scene_name: str | None) -> Path | None:
    """Locate the rendered mp4 under Manim's media layout."""
    candidates = sorted(
        out_root.rglob('*.mp4'),
        key=lambda p: p.stat().st_size, reverse=True,  # prefer the largest render
    )
    if not candidates:
        return None
    if scene_name:
        for path in candidates:
            if scene_name in path.name:
                return path
    return candidates[0]


def render_script(script_source: str, scene_name: str | None = None,
                  quality: str = 'medium', timeout: int = DEFAULT_TIMEOUT,
                  still: bool = False) -> dict:
    """Render a Manim script; return {'success', 'video_path'|'error', 'duration_ms'}.

    The script is validated with ``script_validator`` first — invalid scripts
    are rejected without spawning Manim. ``still=True`` renders only the
    last frame (Manim -s) and returns {'success', 'image_path', ...} instead.
    """
    from .script_validator import validate_script

    problems = validate_script(script_source)
    if problems:
        return {
            'success': False,
            'error': '脚本校验失败: ' + '; '.join(problems),
            'duration_ms': 0,
        }

    quality_flag = QUALITY_FLAGS.get(quality, '-qm')
    start = time.time()

    with tempfile.TemporaryDirectory(prefix='manim_render_') as tmp:
        script_path = Path(tmp) / 'scene.py'
        script_path.write_text(script_source, encoding='utf-8')
        out_root = Path(tmp) / 'output'

        cmd = ['manim', quality_flag, '--media_dir', str(out_root)]
        if still:
            cmd.append('-s')  # render the LAST frame only (text-to-image)
        if scene_name:
            cmd += [str(script_path), scene_name]
        else:
            cmd += [str(script_path)]

        try:
            completed = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': f'渲染超时（{timeout} 秒）',
                'duration_ms': int((time.time() - start) * 1000),
            }

        duration_ms = int((time.time() - start) * 1000)

        if completed.returncode != 0:
            stderr = (completed.stderr or '').strip().splitlines()
            return {
                'success': False,
                'error': 'Manim 渲染失败: ' + (stderr[-1] if stderr else f'exit {completed.returncode}'),
                'duration_ms': duration_ms,
            }

        if still:
            images = sorted(out_root.rglob('*.png'))
            if not images:
                return {
                    'success': False,
                    'error': '渲染完成但未找到静帧图片',
                    'duration_ms': duration_ms,
                }
            dest = _output_dir() / f'{images[-1].stem}_{int(time.time())}.png'
            shutil.copy2(images[-1], dest)
            return {
                'success': True,
                'image_path': str(dest),
                'duration_ms': duration_ms,
            }

        rendered = _find_rendered_video(out_root, scene_name)
        if rendered is None:
            return {
                'success': False,
                'error': '渲染完成但未找到输出视频文件',
                'duration_ms': duration_ms,
            }

        # Copy into the stable output dir (media/videos/)
        dest = _output_dir() / f'{rendered.stem}_{int(time.time())}.mp4'
        shutil.copy2(rendered, dest)

        return {
            'success': True,
            'video_path': str(dest),
            'duration_ms': duration_ms,
        }
