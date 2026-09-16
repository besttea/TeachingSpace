"""Tests for the video generation pipeline (validator + Manim engine).

The engine test performs a REAL Manim render (low quality, ~5s on a warm
cache) — requires the manim CLI to be installed. Renders go to a temp dir
so media/ is never polluted by tests.
"""

import shutil
import tempfile

from django.test import SimpleTestCase, override_settings

from .manim_engine import render_script
from .script_validator import validate_script

_MEDIA_TMP = tempfile.mkdtemp(prefix='manim_test_')

GOOD_SCENE = '''
from manim import *

class HelloScene(Scene):
    def construct(self):
        t = Text("Hello Manim")
        self.play(Write(t))
        self.wait(0.1)
'''


class ScriptValidatorTests(SimpleTestCase):
    def test_valid_scene_passes(self):
        self.assertEqual(validate_script(GOOD_SCENE), [])

    def test_forbidden_import_rejected(self):
        problems = validate_script('import os\nfrom manim import *\nclass S(Scene):\n    def construct(self):\n        os.system("x")')
        self.assertTrue(any('import' in p for p in problems))

    def test_forbidden_call_rejected(self):
        problems = validate_script(
            'from manim import *\nclass S(Scene):\n    def construct(self):\n        open("/etc/passwd")')
        self.assertTrue(any('open' in p for p in problems))

    def test_missing_scene_rejected(self):
        problems = validate_script('x = 1')
        self.assertTrue(any('Scene' in p for p in problems))

    def test_syntax_error_rejected(self):
        problems = validate_script('def broken(:')
        self.assertTrue(any('语法' in p for p in problems))


@override_settings(MANIM_OUTPUT_DIR=_MEDIA_TMP)
class ManimEngineTests(SimpleTestCase):
    def test_real_render_produces_video(self):
        if shutil.which('manim') is None:
            self.skipTest('manim CLI not installed')
        result = render_script(GOOD_SCENE, scene_name='HelloScene',
                               quality='low', timeout=240)
        self.assertTrue(result['success'], result.get('error'))
        self.assertTrue(result['video_path'].endswith('.mp4'))

    def test_invalid_script_rejected_before_render(self):
        result = render_script('import os\nx = 1', quality='low', timeout=60)
        self.assertFalse(result['success'])
        self.assertIn('校验失败', result['error'])
