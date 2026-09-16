"""Shared helpers for AI-assisted exam question modification.

Used by the ``modify_exam`` management command AND the web endpoint
(examination views) — one source of truth for the question<->dict
conversion and the apply logic.
"""

from apps.examination.models import (
    CodeQuestion, EssayQuestion, MultipleChoiceQuestion, Question,
    TrueFalseQuestion,
)


def question_to_dict(question: Question) -> dict:
    """Serialize a question (with its specific type fields) to a plain dict."""
    data = {
        'type': question.question_type,
        'text': question.question_text,
        'points': question.points,
        'difficulty': question.difficulty,
    }
    specific = question.get_specific_question()
    if isinstance(specific, MultipleChoiceQuestion):
        data.update(options=specific.options,
                    correct_answer=specific.correct_answer,
                    explanation=specific.explanation)
    elif isinstance(specific, TrueFalseQuestion):
        data.update(correct_answer=specific.correct_answer,
                    explanation=specific.explanation)
    elif isinstance(specific, CodeQuestion):
        data.update(starter_code=specific.starter_code,
                    solution_code=specific.solution_code,
                    test_cases=specific.test_cases,
                    explanation=specific.explanation)
    elif isinstance(specific, EssayQuestion):
        data.update(word_limit=specific.word_limit,
                    rubric=specific.rubric,
                    sample_answer=specific.sample_answer)
    return data


def apply_question(question: Question, updated: dict):
    """Write an updated question dict back to the DB (skill-mode apply)."""
    question.question_text = updated.get('text', question.question_text)
    question.points = int(updated.get('points', question.points))
    question.save()

    specific = question.get_specific_question()
    if isinstance(specific, MultipleChoiceQuestion):
        specific.options = updated.get('options', specific.options)
        specific.correct_answer = updated.get('correct_answer', specific.correct_answer)
        specific.explanation = updated.get('explanation', specific.explanation)
        specific.save()
    elif isinstance(specific, TrueFalseQuestion):
        specific.correct_answer = bool(updated.get('correct_answer', specific.correct_answer))
        specific.explanation = updated.get('explanation', specific.explanation)
        specific.save()
    elif isinstance(specific, CodeQuestion):
        specific.starter_code = updated.get('starter_code', specific.starter_code)
        specific.solution_code = updated.get('solution_code', specific.solution_code)
        specific.test_cases = updated.get('test_cases', specific.test_cases)
        specific.explanation = updated.get('explanation', specific.explanation)
        specific.save()
    elif isinstance(specific, EssayQuestion):
        specific.word_limit = int(updated.get('word_limit') or 0)
        specific.rubric = updated.get('rubric', specific.rubric)
        specific.sample_answer = updated.get('sample_answer', specific.sample_answer)
        specific.save()


def validate_code_question(updated: dict):
    """Sandbox-validate an updated code question (solution vs test cases).

    Returns (ok, message). Non-code questions are always ok.
    """
    if updated.get('type') != 'code':
        return True, ''
    from apps.ai_agents.training_agent import validate_exercise
    ok, message, _detail = validate_exercise(
        updated.get('solution_code', ''),
        updated.get('test_cases', []))
    return ok, message
