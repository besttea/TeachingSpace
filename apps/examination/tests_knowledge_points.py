"""Knowledge-point-driven exam generation tests: distinct-first KP
distribution, prompt injection, M2M binding and the view/task wiring
(plan step 9)."""

import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.learning.models import Chapter, Course, KnowledgePoint
from apps.ai_agents.skills.exam_skill import ExamSkill
from .exam_assembly import save_generated_questions
from .models import Exam, Question

MC = {'type': 'multiple_choice', 'text': 'Q?', 'points': 4,
      'options': {'A': 'x', 'B': 'y', 'C': 'z', 'D': 'w'}, 'correct_answer': 'A'}


class ExamSkillKPDistributionTests(TestCase):
    def _fake_call(self, prompts):
        def fake(prompt, **kwargs):
            prompts.append(prompt)
            if 'Plan a' in prompt:
                return {'types': ['multiple_choice'] * 6}
            return dict(MC, text=f'Q{len([p for p in prompts if "Create ONE" in p])}')
        return fake

    def test_distinct_first_round_robin(self):
        prompts = []
        kps = [{'id': 1, 'title': '列表', 'description': 'dA'},
               {'id': 2, 'title': '元组', 'description': 'dB'}]
        with mock.patch('apps.ai_agents.skills.exam_skill.HarnessCore.call',
                        side_effect=self._fake_call(prompts)):
            result = ExamSkill().run('Python 基础', count=6,
                                     knowledge_points=kps)
        self.assertEqual(len(result['questions']), 6)
        ids = [q['_knowledge_point_id'] for q in result['questions']]
        self.assertEqual(ids, [1, 2, 1, 2, 1, 2])

        worker_prompts = [p for p in prompts if 'Create ONE' in p]
        self.assertIn('Target knowledge point', worker_prompts[0])
        self.assertIn('列表', worker_prompts[0])
        self.assertIn('元组', worker_prompts[1])
        planner = next(p for p in prompts if 'Plan a' in p)
        self.assertIn('列表', planner)
        self.assertIn('元组', planner)
        self.assertIn('never repeating', planner)

    def test_no_kps_prompt_unchanged(self):
        prompts = []
        with mock.patch('apps.ai_agents.skills.exam_skill.HarnessCore.call',
                        side_effect=self._fake_call(prompts)):
            ExamSkill().run('Python 基础', count=2)
        worker_prompts = [p for p in prompts if 'Create ONE' in p]
        self.assertNotIn('Target knowledge point', worker_prompts[0])
        self.assertNotIn('never repeating',
                         next(p for p in prompts if 'Plan a' in p))


class SaveGeneratedQuestionsKPTests(TestCase):
    def setUp(self):
        instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='KP 考试课程', slug='kp-exam-course',
            instructor=instructor, difficulty_level='beginner')
        self.kp = KnowledgePoint.objects.create(
            course=self.course, title='列表推导式')
        self.exam = Exam.objects.create(
            title='KP 卷', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, course=self.course,
            created_by=instructor)

    def test_m2m_bound_from_knowledge_point_id(self):
        summary = save_generated_questions(self.exam, [
            dict(MC, _knowledge_point_id=self.kp.id)])
        self.assertEqual(summary['saved'], 1)
        question = Question.objects.get(exam=self.exam)
        self.assertEqual(list(question.knowledge_points.all()), [self.kp])

    def test_unknown_kp_id_skipped_silently(self):
        summary = save_generated_questions(self.exam, [
            dict(MC, _knowledge_point_id=9999)])
        self.assertEqual(summary['saved'], 1)
        question = Question.objects.get(exam=self.exam)
        self.assertEqual(question.knowledge_points.count(), 0)

    def test_kp_id_not_persisted_as_text(self):
        save_generated_questions(self.exam, [
            dict(MC, _knowledge_point_id=self.kp.id)])
        question = Question.objects.get(exam=self.exam)
        self.assertFalse(hasattr(question, '_knowledge_point_id'))


class ExamAIGenerateKPTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='KP 课程', slug='kp-course', instructor=self.instructor,
            difficulty_level='beginner')
        Chapter.objects.create(course=self.course, title='第1章', order=1)
        KnowledgePoint.objects.create(course=self.course, title='列表',
                                      description='d1')
        KnowledgePoint.objects.create(course=self.course, title='字典',
                                      description='d2')
        self.exam = Exam.objects.create(
            title='KP 卷', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, course=self.course,
            created_by=self.instructor)
        self.client.force_login(self.instructor)

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExamSkill')
    def test_view_passes_course_kps_to_skill(self, skill_cls, _cfg):
        skill_cls.return_value.run.return_value = {
            'questions': [dict(MC, _knowledge_point_id=1),
                          dict(MC, _knowledge_point_id=2)],
            'code_validated': '0/0',
        }
        response = self.client.post(
            reverse('examination:exam-ai-generate', args=[self.exam.id]),
            data=json.dumps({'count': 2}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        run_kwargs = skill_cls.return_value.run.call_args.kwargs
        kps = run_kwargs['knowledge_points']
        self.assertEqual(len(kps), 2)
        self.assertEqual({kp['title'] for kp in kps}, {'列表', '字典'})
        # eager run bound the M2M on saved questions
        self.assertEqual(self.exam.questions.count(), 2)
        bound = set()
        for question in self.exam.questions.all():
            bound.update(question.knowledge_points.values_list('title',
                                                               flat=True))
        self.assertEqual(bound, {'列表', '字典'})

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExamSkill')
    def test_exam_without_course_passes_no_kps(self, skill_cls, _cfg):
        exam = Exam.objects.create(
            title='无课程卷', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, created_by=self.instructor)
        skill_cls.return_value.run.return_value = {
            'questions': [dict(MC)], 'code_validated': '0/0'}
        self.client.post(reverse('examination:exam-ai-generate',
                                 args=[exam.id]),
                         data=json.dumps({'count': 1}),
                         content_type='application/json')
        self.assertIsNone(
            skill_cls.return_value.run.call_args.kwargs['knowledge_points'])


class ExamCreateCourseLinkTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.other = User.objects.create_user(
            username='other', email='o@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='我的课', slug='my-course', instructor=self.instructor,
            difficulty_level='beginner')
        self.foreign = Course.objects.create(
            title='别人的课', slug='foreign-course', instructor=self.other,
            difficulty_level='beginner')
        self.client.force_login(self.instructor)

    def _create(self, course_id=''):
        data = {'title': '链接卷', 'description': 'x',
                'duration_minutes': 30, 'passing_score': 60,
                'max_attempts': 3}
        if course_id:
            data['course_id'] = course_id
        return self.client.post(reverse('examination:exam-create'), data)

    def test_create_with_own_course_links_it(self):
        response = self._create(self.course.id)
        self.assertRedirects(response, reverse('examination:exam-manage'))
        exam = Exam.objects.get(title='链接卷')
        self.assertEqual(exam.course, self.course)

    def test_foreign_course_ignored(self):
        self._create(self.foreign.id)
        exam = Exam.objects.get(title='链接卷')
        self.assertIsNone(exam.course)

    def test_form_lists_own_courses_only(self):
        response = self.client.get(reverse('examination:exam-create'))
        self.assertContains(response, '我的课')
        self.assertNotContains(response, '别人的课')


class QuestionEditKPTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='KP 课程', slug='kp-edit-course', instructor=self.instructor,
            difficulty_level='beginner')
        self.kp = KnowledgePoint.objects.create(course=self.course,
                                                title='列表推导式')
        self.exam = Exam.objects.create(
            title='KP 卷', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, course=self.course,
            created_by=self.instructor)
        self.question = Question.objects.create(
            exam=self.exam, question_type='true_false',
            question_text='TF?', points=2, order=0)
        from .models import TrueFalseQuestion
        TrueFalseQuestion.objects.create(question=self.question,
                                         correct_answer=True)
        self.client.force_login(self.instructor)

    def test_edit_page_shows_kp_selection(self):
        response = self.client.get(reverse(
            'examination:question-edit', args=[self.question.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '列表推导式')
        self.assertEqual(len(response.context['available_kps']), 1)

    def test_edit_post_sets_kps(self):
        response = self.client.post(
            reverse('examination:question-edit', args=[self.question.id]), {
                'text': 'TF?', 'points': 2,
                'correct_answer': 'true', 'explanation': '',
                'knowledge_points': [str(self.kp.id)],
            })
        self.assertRedirects(response, reverse('examination:exam-manage'))
        self.assertEqual(list(self.question.knowledge_points.all()), [self.kp])

    def test_edit_post_clears_kps_when_none_selected(self):
        self.question.knowledge_points.add(self.kp)
        self.client.post(
            reverse('examination:question-edit', args=[self.question.id]), {
                'text': 'TF?', 'points': 2,
                'correct_answer': 'true', 'explanation': '',
            })
        self.assertEqual(self.question.knowledge_points.count(), 0)

    def test_clone_copies_kps(self):
        from .question_ai import clone_question
        self.question.knowledge_points.add(self.kp)
        target = Exam.objects.create(
            title='目标卷', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, course=self.course,
            created_by=self.instructor)
        clone = clone_question(self.question, target, order=0)
        self.assertEqual(list(clone.knowledge_points.all()), [self.kp])


class ExamAIGenerateKPSubsetTests(TestCase):
    """Plan v3 1.2: instructors scope whole-exam generation to a KP subset."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.instructor = User.objects.create_user(
            username='teacher', email='t@example.com',
            password='StrongPass123!', user_type='instructor')
        self.course = Course.objects.create(
            title='KP 课程', slug='kp-subset', instructor=self.instructor,
            difficulty_level='beginner')
        self.kp_a = KnowledgePoint.objects.create(course=self.course, title='A')
        self.kp_b = KnowledgePoint.objects.create(course=self.course, title='B')
        self.exam = Exam.objects.create(
            title='子集卷', description='x', duration_minutes=30,
            passing_score=60, max_attempts=3, course=self.course,
            created_by=self.instructor)
        self.client.force_login(self.instructor)

    def _post(self, **payload):
        return self.client.post(
            reverse('examination:exam-ai-generate', args=[self.exam.id]),
            data=json.dumps(payload), content_type='application/json')

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExamSkill')
    def test_subset_selection_reaches_skill(self, skill_cls, _cfg):
        skill_cls.return_value.run.return_value = {
            'questions': [], 'code_validated': '0/0'}
        response = self._post(count=2, knowledge_point_ids=[self.kp_a.id])
        self.assertEqual(response.status_code, 200)
        kps = skill_cls.return_value.run.call_args.kwargs['knowledge_points']
        self.assertEqual([kp['title'] for kp in kps], ['A'])

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    @mock.patch('apps.ai_agents.skills.ExamSkill')
    def test_omitted_selection_uses_all_kps(self, skill_cls, _cfg):
        skill_cls.return_value.run.return_value = {
            'questions': [], 'code_validated': '0/0'}
        response = self._post(count=2)
        self.assertEqual(response.status_code, 200)
        kps = skill_cls.return_value.run.call_args.kwargs['knowledge_points']
        self.assertEqual({kp['title'] for kp in kps}, {'A', 'B'})

    @mock.patch('apps.ai_agents.ai_config.is_configured', return_value=True)
    def test_foreign_kp_ids_rejected(self, _cfg):
        response = self._post(count=2, knowledge_point_ids=[99999])
        self.assertEqual(response.status_code, 400)
        self.assertIn('不属于关联课程', response.json()['error'])

    def test_knowledge_points_endpoint(self):
        response = self.client.get(reverse(
            'examination:exam-ai-knowledge-points', args=[self.exam.id]))
        self.assertEqual(response.status_code, 200)
        titles = {kp['title'] for kp in response.json()['knowledge_points']}
        self.assertEqual(titles, {'A', 'B'})

    def test_knowledge_points_endpoint_forbidden(self):
        other = User.objects.create_user(
            username='other', email='o@example.com',
            password='StrongPass123!', user_type='instructor')
        self.client.force_login(other)
        response = self.client.get(reverse(
            'examination:exam-ai-knowledge-points', args=[self.exam.id]))
        self.assertEqual(response.status_code, 403)
