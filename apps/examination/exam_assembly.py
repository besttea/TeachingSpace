"""Shared helpers for turning AI-generated question dicts into Exam rows.

Single source of truth for the generate_exam management command, the
Celery task behind the web AI-generation flow and question-bank import.
"""

import logging

from .models import (
    CodeQuestion, EssayQuestion, MultipleChoiceQuestion,
    Question, TrueFalseQuestion,
)

logger = logging.getLogger(__name__)


def save_generated_questions(exam, questions: list) -> dict:
    """Create Question + typed detail rows from ExamSkill output dicts.

    Returns {'saved': n, 'skipped': n, 'code_validated': 'x/y'}.
    Never raises for a bad row — bad questions are skipped and counted.
    """
    saved = 0
    skipped = 0
    validated_code = 0
    code_total = 0
    valid_types = set(dict(Question.QUESTION_TYPES))

    for index, q in enumerate(questions):
        q_type = q.get('type')
        if q_type not in valid_types:
            logger.warning('exam %s: question %s has unknown type %r — skipped',
                           exam.id, index, q_type)
            skipped += 1
            continue
        try:
            question = Question.objects.create(
                exam=exam,
                question_type=q_type,
                question_text=q.get('text', ''),
                points=int(q.get('points', 10)),
                difficulty='medium',
                order=index,
            )
            # Bind the assigned knowledge point (guarded: the KP may have
            # been deleted between queue and run).
            kp_id = q.get('_knowledge_point_id')
            if kp_id:
                from .models import KnowledgePoint
                kp = KnowledgePoint.objects.filter(pk=kp_id).first()
                if kp is not None:
                    question.knowledge_points.add(kp)
            if q_type == 'multiple_choice':
                MultipleChoiceQuestion.objects.create(
                    question=question,
                    options=q.get('options', {}),
                    correct_answer=q.get('correct_answer', 'A'),
                    explanation=q.get('explanation', ''),
                )
            elif q_type == 'true_false':
                TrueFalseQuestion.objects.create(
                    question=question,
                    correct_answer=bool(q.get('correct_answer', False)),
                    explanation=q.get('explanation', ''),
                )
            elif q_type == 'code':
                code_total += 1
                CodeQuestion.objects.create(
                    question=question,
                    starter_code=q.get('starter_code', ''),
                    solution_code=q.get('solution_code', ''),
                    test_cases=q.get('test_cases', []),
                    explanation=q.get('explanation', ''),
                )
                if q.get('_validated'):
                    validated_code += 1
            elif q_type == 'essay':
                EssayQuestion.objects.create(
                    question=question,
                    word_limit=int(q.get('word_limit') or 0),
                    rubric=q.get('rubric', ''),
                    sample_answer=q.get('sample_answer', ''),
                )
            saved += 1
        except Exception as e:
            logger.warning('exam %s: question %s failed to save: %s', exam.id, index, e)
            skipped += 1

    return {
        'saved': saved,
        'skipped': skipped,
        'code_validated': f'{validated_code}/{code_total}',
    }
