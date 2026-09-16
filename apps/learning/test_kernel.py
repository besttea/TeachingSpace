"""Tests for the real Jupyter kernel sessions (learning class).

Spawns actual ipykernel processes (local backend). Each test gets its own
kernel (deterministic, no cross-test state) and kernels are shut down in
tearDown. Skips cleanly when jupyter_client is not installed.
"""

import itertools
import unittest

from django.test import SimpleTestCase, override_settings

from .jupyter_kernel import HAS_JUPYTER, manager

_id_counter = itertools.count(910000)


@unittest.skipUnless(HAS_JUPYTER, 'jupyter_client/ipykernel not installed')
class JupyterKernelTests(SimpleTestCase):
    """Notebook semantics: state, rich output, errors, restart, timeout."""

    def setUp(self):
        # fresh kernel per test — no cross-test state
        self.uid = next(_id_counter)

    def tearDown(self):
        manager.shutdown_all()

    def test_state_persists_across_cells(self):
        result = manager.execute(self.uid, self.uid, 'x = 21\ny = 2')
        self.assertIsNotNone(result['execution_count'])
        result = manager.execute(self.uid, self.uid, 'print(x * y)')
        stream_text = ''.join(
            o['text'] for o in result['outputs'] if o['type'] == 'stream')
        self.assertIn('42', stream_text)

    def test_error_output_with_state_preserved(self):
        manager.execute(self.uid, self.uid, 'keep = 123')
        result = manager.execute(self.uid, self.uid, '1/0')
        errors = [o for o in result['outputs'] if o['type'] == 'error']
        self.assertTrue(errors)
        self.assertEqual(errors[0]['ename'], 'ZeroDivisionError')
        # session survives the error
        result = manager.execute(self.uid, self.uid, 'print(keep)')
        stream_text = ''.join(
            o['text'] for o in result['outputs'] if o['type'] == 'stream')
        self.assertIn('123', stream_text)

    def test_matplotlib_rich_output(self):
        # the session's inline backend (set at kernel startup) renders plots
        # as display_data — no manual backend switching
        result = manager.execute(
            self.uid, self.uid,
            "import matplotlib.pyplot as plt\n"
            "plt.plot([1, 2, 3], [1, 4, 9])\nplt.title('test')")
        images = [o for o in result['outputs']
                  if o['type'] == 'display_data' and 'image/png' in o['data']]
        self.assertTrue(images)
        self.assertGreater(len(images[0]['data']['image/png']), 1000)

    def test_restart_clears_variables(self):
        manager.execute(self.uid, self.uid, 'gone = 42')
        manager.restart(self.uid, self.uid)
        result = manager.execute(self.uid, self.uid,
                                 'try:\n    print(gone)\nexcept NameError:\n    print("cleared")')
        stream_text = ''.join(
            o['text'] for o in result['outputs'] if o['type'] == 'stream')
        self.assertIn('cleared', stream_text)

    @override_settings(JUPYTER_EXECUTE_TIMEOUT=2)
    def test_runaway_code_interrupted_not_killed(self):
        result = manager.execute(self.uid, self.uid,
                                 'import time\ntime.sleep(30)')
        errors = [o for o in result['outputs'] if o['type'] == 'error']
        self.assertTrue(errors)
        self.assertEqual(errors[-1]['ename'], 'TimeoutError')
        # the session is still usable (interrupt, not kill)
        result = manager.execute(self.uid, self.uid, 'print("alive")')
        stream_text = ''.join(
            o['text'] for o in result['outputs'] if o['type'] == 'stream')
        self.assertIn('alive', stream_text)
