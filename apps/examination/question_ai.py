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


def recompute_exam_scores(exam) -> int:
    """Recompute score/is_passing for all SUBMITTED attempts of an exam.

    Called after manual grading in admin, or after AI question modification
    changes point values. Returns the number of attempts recomputed.
    """
    attempts = exam.student_attempts.filter(is_submitted=True)
    updated = 0
    for attempt in attempts:
        new_score = attempt.calculate_score()
        if attempt.score != new_score:
            attempt.score = new_score
            attempt.save()
            updated += 1
    return updated


def clone_question(source: 'Question', target_exam, order: int):
    """Clone a question (with its specific record) into another exam.

    Used by assemble_exam; code questions must be validated by the caller.
    """
    from apps.examination.models import (
        CodeQuestion, EssayQuestion, MultipleChoiceQuestion,
        Question, TrueFalseQuestion,
    )

    question = Question.objects.create(
        exam=target_exam,
        question_type=source.question_type,
        question_text=source.question_text,
        points=source.points,
        difficulty=source.difficulty,
        order=order,
    )
    specific = source.get_specific_question()
    if isinstance(specific, MultipleChoiceQuestion):
        MultipleChoiceQuestion.objects.create(
            question=question, options=specific.options,
            correct_answer=specific.correct_answer,
            explanation=specific.explanation)
    elif isinstance(specific, TrueFalseQuestion):
        TrueFalseQuestion.objects.create(
            question=question, correct_answer=specific.correct_answer,
            explanation=specific.explanation)
    elif isinstance(specific, CodeQuestion):
        CodeQuestion.objects.create(
            question=question, starter_code=specific.starter_code,
            solution_code=specific.solution_code,
            test_cases=specific.test_cases,
            explanation=specific.explanation)
    elif isinstance(specific, EssayQuestion):
        EssayQuestion.objects.create(
            question=question, word_limit=specific.word_limit,
            rubric=specific.rubric, sample_answer=specific.sample_answer)
    return question


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
