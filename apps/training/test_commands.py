"""Management-command coverage: load_sample_exercises (seeding + idempotency)."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .models import Exercise, Hint


class LoadSampleExercisesTests(TestCase):
    def test_creates_exercises_with_hints(self):
        call_command('load_sample_exercises', stdout=StringIO())
        self.assertGreaterEqual(Exercise.objects.count(), 2)
        exercise = Exercise.objects.get(slug='sum-of-two-numbers')
        self.assertEqual(exercise.difficulty, 'beginner')
        self.assertTrue(Hint.objects.filter(exercise=exercise).exists())

    def test_idempotent(self):
        call_command('load_sample_exercises', stdout=StringIO())
        first = Exercise.objects.count()
        call_command('load_sample_exercises', stdout=StringIO())
        self.assertEqual(Exercise.objects.count(), first)
