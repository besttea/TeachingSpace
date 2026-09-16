"""Video thumbnails and async rendering (T21)."""

import logging
import subprocess
from pathlib import Path

from celery import shared_task

from .manim_engine import render_script

logger = logging.getLogger(__name__)


def generate_thumbnail(video_path: str, out_path: str, at_seconds: float = 1.0) -> bool:
    """Extract a frame as JPEG via ffmpeg. Returns success."""
    import shutil

    if shutil.which('ffmpeg') is None:
        logger.warning('ffmpeg not found — thumbnail skipped')
        return False
    try:
        completed = subprocess.run(
            ['ffmpeg', '-y', '-ss', str(at_seconds), '-i', video_path,
             '-frames:v', '1', '-q:v', '3', out_path],
            capture_output=True, text=True, timeout=60)
        return completed.returncode == 0 and Path(out_path).exists()
    except (subprocess.TimeoutExpired, OSError):
        return False


@shared_task
def render_video_task(script_source, scene_name=None, quality='medium',
                      timeout=300):
    """Celery wrapper for Manim rendering (eager inline without a broker)."""
    return render_script(script_source, scene_name=scene_name,
                         quality=quality, timeout=timeout)
