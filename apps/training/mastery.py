"""Student knowledge-point mastery computation (plan v3 2.1).

Pure query layer (no models defined here) — maps the student's exercise
submissions and exam answers onto the knowledge points of their enrolled
courses. Returns plain dicts for the template; per-student scale is small,
so a few grouped queries beat per-KP lookups.

State: 未开始 (no signals) / 学习中 (0 < score < 0.7) / 已掌握 (>= 0.7).
"""

from collections import defaultdict

from django.db.models import Count, Q


def kp_mastery(student, course) -> list:
    """Mastery rows for every knowledge point of one course."""
    from apps.training.models import Exercise, Submission
    from apps.examination.models import ExamAnswer

    kps = list(course.knowledge_points.select_related('chapter').order_by('order', 'id'))
    if not kps:
        return []
    kp_ids = [kp.id for kp in kps]

    # Exercises bound to these KPs and their latest submission per exercise.
    exercises = list(Exercise.objects.filter(
        knowledge_points__in=kp_ids).distinct())
    exercise_ids = [e.id for e in exercises]
    latest_subs = {}
    if exercise_ids:
        submissions = Submission.objects.filter(
            student=student, exercise_id__in=exercise_ids
        ).order_by('exercise_id', '-submitted_at', '-id')
        for sub in submissions:
            latest_subs.setdefault(sub.exercise_id, sub)

    # Exercise signal per KP: 1 when the latest attempt of an exercise bound
    # to that KP passed, 0 when it did not.
    exercise_signals = defaultdict(lambda: [0, 0])  # kp_id -> [passed, total]
    exercise_by_kp = defaultdict(list)
    for exercise in exercises:
        for kp in exercise.knowledge_points.all():
            exercise_by_kp[kp.id].append(exercise.id)
    for kp_id, ids in exercise_by_kp.items():
        for exercise_id in ids:
            sub = latest_subs.get(exercise_id)
            if sub is None:
                continue
            exercise_signals[kp_id][1] += 1
            if sub.status == 'passed':
                exercise_signals[kp_id][0] += 1

    # Exam signal per KP: correct / graded answers on questions bound to it
    # (submitted attempts of exams linked to this course).
    exam_signals = defaultdict(lambda: [0, 0])
    answer_rows = (
        ExamAnswer.objects.filter(
            student_exam__student=student,
            student_exam__is_submitted=True,
            student_exam__exam__course=course,
            question__knowledge_points__in=kp_ids,
            is_correct__isnull=False,
        )
        .values('question__knowledge_points')
        .annotate(total=Count('id'),
                  correct=Count('id', filter=Q(is_correct=True))))
    for row in answer_rows:
        kp_id = row['question__knowledge_points']
        exam_signals[kp_id] = [row['correct'], row['total']]

    rows = []
    for kp in kps:
        e_passed, e_total = exercise_signals[kp.id]
        x_correct, x_total = exam_signals[kp.id]
        signals = e_total + x_total
        if signals == 0:
            score, state = None, '未开始'
        else:
            score = (e_passed + x_correct) / signals
            state = '已掌握' if score >= 0.7 else '学习中'
        rows.append({
            'kp': kp,
            'exercise_total': e_total,
            'exercise_passed': e_passed,
            'exam_total': x_total,
            'exam_correct': x_correct,
            'score': round(score * 100) if score is not None else None,
            'state': state,
        })
    return rows
