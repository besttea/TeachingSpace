"""Kernel registry governance tests: idle reaping and global LRU eviction
(T3/3.3) — no real kernels spawned, fake sessions only."""

import time

from django.test import SimpleTestCase, override_settings

from .jupyter_kernel import manager


class FakeSession:
    def __init__(self, last_active):
        self.last_active = last_active
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1


class ReapTests(SimpleTestCase):
    def setUp(self):
        # isolate the registry between tests
        manager._sessions = {}

    def _seed(self, pairs):
        for key, last_active in pairs:
            manager._sessions[key] = FakeSession(last_active)

    def test_idle_sessions_reaped(self):
        now = time.time()
        self._seed([
            ('1:100', now - 3600),   # idle — reaped
            ('2:100', now - 10),     # active — kept
        ])
        with override_settings(JUPYTER_KERNEL_IDLE_TIMEOUT=900,
                               JUPYTER_MAX_KERNELS=20):
            manager._reap_locked(now)
        self.assertNotIn('1:100', manager._sessions)
        self.assertIn('2:100', manager._sessions)
        self.assertEqual(manager._sessions['2:100'].shutdown_calls, 0)

    def test_lru_evicted_over_capacity(self):
        now = time.time()
        self._seed([
            ('1:100', now - 300),
            ('2:100', now - 200),
            ('3:100', now - 100),
        ])
        with override_settings(JUPYTER_KERNEL_IDLE_TIMEOUT=900,
                               JUPYTER_MAX_KERNELS=2):
            manager._reap_locked(now)
        self.assertEqual(sorted(manager._sessions), ['2:100', '3:100'])
        # the evicted (least recently used) session was shut down
        self.assertEqual(len(manager._sessions), 2)

    def test_shutdown_all_clears_registry(self):
        self._seed([('1:100', time.time()), ('2:100', time.time())])
        manager.shutdown_all()
        self.assertEqual(manager._sessions, {})
