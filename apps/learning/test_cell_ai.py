"""Cell-level AI generation tests: the four skills (text/code/image/video),
their endpoints and the async video task (lesson editor AI toolbar)."""

import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from .models import Cell, Chapter, Course, Lesson


def _make_user(username, user_type='instructor'):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com',
        password='StrongPass123!', user_type=user_type)


class CellAISetup(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = _make_user('teacher')
        self.student = _make_user('student', 'student')
        self.course = Course.objects.create(
            title='AI 单元格课程', slug='ai-cell-course',
            instructor=self.instructor, difficulty_level='beginner')
        chapter = Chapter.objects.create(course=self.course, title='第1章',
                                         order=1)
        self.lesson = Lesson.objects.create(chapter=chapter, title='单元1',
                                            order=1, status='published')
        self.text_cell = Cell.objects.create(
            lesson=self.lesson, cell_type='text', order=0, data={'markdown': ''})
        self.code_cell = Cell.objects.create(
            lesson=self.lesson, cell_type='code', order=1,
            data={'source': '', 'output': '', 'execution_count': 0})
        self.image_cell = Cell.objects.create(
            lesson=self.lesson, cell_type='image', order=2,
            data={'url': '', 'caption': '', 'alt_text': ''})
        self.video_cell = Cell.objects.create(
            lesson=self.lesson, cell_type='video', order=3,
            data={'url': '', 'source_type': 'youtube', 'caption': ''})
        self.client.force_login(self.instructor)

    def _post(self, url_name, cell, payload):
        return self.client.post(reverse(url_name, args=[cell.id]),
                                data=json.dumps(payload),
                                content_type='application/json')


class CellSkillTests(TestCase):
    """The four cell skills against a mocked harness."""

    def _patch(self, return_value):
        patcher = mock.patch(
            'apps.ai_agents.skills.cell_skills.HarnessCore.call',
            return_value=return_value)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_text_skill(self):
        call_mock = self._patch('## 标题\n\n正文内容')
        from apps.ai_agents.skills import TextSkill
        result = TextSkill().run('列表', context='素材')
        self.assertIn('正文内容', result['content'])
        prompt = call_mock.call_args[0][0]
        self.assertIn('Ground the content in this material', prompt)

    def test_code_skill_strips_nothing_extra(self):
        self._patch('```python\nprint(1)\n```')
        from apps.ai_agents.skills import CodeSkill
        result = CodeSkill().run('打印')
        self.assertEqual(result['content'], '```python\nprint(1)\n```')

    def test_image_skill_strips_fences(self):
        self._patch('```python\nfrom manim import *\n```')
        from apps.ai_agents.skills import ImageSkill
        result = ImageSkill().run('螺旋')
        self.assertEqual(result['script'], 'from manim import *')

    def test_video_skill_strips_fences(self):
        self._patch('```python\nfrom manim import *\nclass S(Scene):\n    pass\n```')
        from apps.ai_agents.skills import VideoSkill
        result = VideoSkill().run('梯度下降')
        self.assertIn('class S(Scene)', result['script'])

    def test_harness_failure_returns_error(self):
        self._patch(None)
        mock.patch(
            'apps.ai_agents.skills.cell_skills.HarnessCore.call',
            side_effect=RuntimeError('boom')).start()
        from apps.ai_agents.skills import TextSkill
        result = TextSkill().run('x')
        self.assertEqual(result['content'], '')
        self.assertIn('boom', result['error'])
        mock.patch.stopall()


class CellAIEndpointTests(CellAISetup):
    def test_student_forbidden_on_all(self):
        self.client.force_login(self.student)
        for name, cell, payload in (
                ('learning:cell-ai-text', self.text_cell, {'topic': 'x'}),
                ('learning:cell-ai-code', self.code_cell, {'topic': 'x'}),
                ('learning:cell-ai-image', self.image_cell, {'description': 'x'}),
                ('learning:cell-ai-video', self.video_cell, {'topic': 'x'})):
            response = self._post(name, cell, payload)
            self.assertEqual(response.status_code, 403, name)
        response = self.client.get(reverse(
            'learning:cell-video-status', args=[self.video_cell.id]))
        self.assertEqual(response.status_code, 403)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=False)
    def test_unconfigured_ai_rejected(self, _cfg):
        response = self._post('learning:cell-ai-text', self.text_cell,
                              {'topic': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('AI 服务未配置', response.json()['error'])

    def test_empty_topic_rejected(self):
        response = self._post('learning:cell-ai-text', self.text_cell,
                              {'topic': '  '})
        self.assertEqual(response.status_code, 400)

    @mock.patch('apps.ai_agents.skills.TextSkill')
    def test_text_endpoint_returns_content(self, skill_cls):
        skill_cls.return_value.run.return_value = {'content': '# 内容'}
        response = self._post('learning:cell-ai-text', self.text_cell,
                              {'topic': '列表'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['content'], '# 内容')

    @mock.patch('apps.ai_agents.skills.CodeSkill')
    def test_code_endpoint_returns_content(self, skill_cls):
        skill_cls.return_value.run.return_value = {'content': 'print(1)'}
        response = self._post('learning:cell-ai-code', self.code_cell,
                              {'topic': '打印'})
        self.assertEqual(response.json()['content'], 'print(1)')

    @mock.patch('apps.ai_agents.skills.ImageSkill')
    @mock.patch('apps.video_generator.manim_engine.render_script')
    def test_image_endpoint_returns_url(self, render_mock, skill_cls):
        skill_cls.return_value.run.return_value = {'script': 'from manim import *'}
        render_mock.return_value = {
            'success': True,
            'image_path': 'media/images/ai/diagram_1.png',
            'duration_ms': 1000}
        with self.settings(MEDIA_ROOT='media', MEDIA_URL='/media/'):
            response = self._post('learning:cell-ai-image', self.image_cell,
                                  {'description': '螺旋'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['url'], '/media/images/ai/diagram_1.png')
        self.assertEqual(body['caption'], '螺旋')
        self.assertTrue(render_mock.call_args.kwargs['still'])

    @mock.patch('apps.ai_agents.skills.ImageSkill')
    @mock.patch('apps.video_generator.manim_engine.render_script')
    def test_image_render_failure_500(self, render_mock, skill_cls):
        skill_cls.return_value.run.return_value = {'script': 'x'}
        render_mock.return_value = {'success': False, 'error': '渲染失败'}
        response = self._post('learning:cell-ai-image', self.image_cell,
                              {'description': '螺旋'})
        self.assertEqual(response.status_code, 500)

    @mock.patch('apps.learning.tasks.generate_cell_video_task')
    def test_video_endpoint_queues_task(self, task_mock):
        response = self._post('learning:cell-ai-video', self.video_cell,
                              {'topic': '梯度下降'})
        self.assertEqual(response.status_code, 200)
        task_mock.delay.assert_called_once()


class CellVideoTaskTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = _make_user('teacher')
        self.course = Course.objects.create(
            title='任务课程', slug='task-video', instructor=self.instructor,
            difficulty_level='beginner')
        chapter = Chapter.objects.create(course=self.course, title='第1章',
                                         order=1)
        self.lesson = Lesson.objects.create(chapter=chapter, title='单元1',
                                            order=1, status='published')
        self.cell = Cell.objects.create(
            lesson=self.lesson, cell_type='video', order=0,
            data={'url': '', 'source_type': 'youtube', 'caption': ''})

    @mock.patch('apps.video_generator.manim_engine.render_script')
    @mock.patch('apps.ai_agents.skills.VideoSkill')
    def test_success_fills_cell_and_creates_video_record(self, skill_cls,
                                                         render_mock):
        skill_cls.return_value.run.return_value = {'script': 'class S(Scene): pass'}
        render_mock.return_value = {
            'success': True,
            'video_path': 'media/videos/scene_1.mp4',
            'duration_ms': 5000}
        with self.settings(MEDIA_ROOT='media', MEDIA_URL='/media/'):
            from .tasks import cell_video_status, generate_cell_video_task
            generate_cell_video_task.delay(self.cell.id, '梯度下降')
            status = cell_video_status(self.cell.id)
        self.assertEqual(status['status'], 'done')
        self.cell.refresh_from_db()
        self.assertEqual(self.cell.data['url'], '/media/videos/scene_1.mp4')
        self.assertEqual(self.cell.data['source_type'], 'manim_generated')
        from .models import Video
        video = Video.objects.get(cell=self.cell)
        self.assertEqual(video.title, '梯度下降')
        self.assertEqual(video.generation_status, 'completed')

    @mock.patch('apps.ai_agents.skills.VideoSkill')
    def test_empty_script_publishes_error(self, skill_cls):
        skill_cls.return_value.run.return_value = {'script': ''}
        from .tasks import cell_video_status, generate_cell_video_task
        generate_cell_video_task.delay(self.cell.id, 'x')
        status = cell_video_status(self.cell.id)
        self.assertEqual(status['status'], 'error')
        self.cell.refresh_from_db()
        self.assertEqual(self.cell.data['url'], '')

    def test_missing_cell_noop(self):
        from .tasks import generate_cell_video_task
        result = generate_cell_video_task.delay(9999, 'x')
        self.assertIsNone(result.result)
