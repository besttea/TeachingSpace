"""Tests for AI generation tracking (history records + daily cost limit)."""

from django.test import TestCase, override_settings

from .models import AIGenerationHistory, daily_cost_exceeded, record_generation


class CostTrackingTests(TestCase):
    def test_record_generation_creates_history(self):
        record_generation(
            agent='TestAgent', model='claude-test',
            prompt='hello', response='world',
            input_tokens=100, output_tokens=50,
        )
        row = AIGenerationHistory.objects.get()
        self.assertEqual(row.agent, 'TestAgent')
        self.assertGreater(float(row.estimated_cost_usd), 0)
        self.assertTrue(row.success)

    def test_failed_generation_recorded_with_error(self):
        record_generation(
            agent='TestAgent', model='claude-test',
            prompt='hello', success=False, error='boom',
        )
        row = AIGenerationHistory.objects.get()
        self.assertFalse(row.success)
        self.assertEqual(row.error, 'boom')

    def test_long_prompt_truncated(self):
        record_generation(
            agent='TestAgent', model='claude-test',
            prompt='x' * 10000, response='y' * 10000,
        )
        row = AIGenerationHistory.objects.get()
        self.assertLess(len(row.prompt), 5000)
        self.assertLess(len(row.response), 5000)

    @override_settings(AI_COST_LIMIT_DAILY=0.001)
    def test_daily_cost_limit_enforced(self):
        self.assertFalse(daily_cost_exceeded())
        # 0.001$ = 1000 input tokens at 3$/1M + overhead
        record_generation(
            agent='TestAgent', model='claude-test', prompt='x',
            input_tokens=1_000_000, output_tokens=0,
        )
        self.assertTrue(daily_cost_exceeded())

    @override_settings(AI_COST_LIMIT_DAILY=0)
    def test_zero_limit_means_disabled(self):
        record_generation(
            agent='TestAgent', model='claude-test', prompt='x',
            input_tokens=1_000_000,
        )
        self.assertFalse(daily_cost_exceeded())
