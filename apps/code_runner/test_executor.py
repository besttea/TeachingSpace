"""Executor transport-level tests: input validation, mode dispatch, docker
backend error paths and result parsing (OPTIMIZATION_PLAN 6.5 coverage gate).

The sandbox semantics themselves (escapes, whitelists, timeouts) are
covered in tests.py; this file exercises the transport branches.
"""

from unittest import mock

from django.test import SimpleTestCase

from .executor import (
    MAX_CODE_LENGTH, CodeExecutor, execute_python_code,
)


class ExecutorValidationTests(SimpleTestCase):
    def test_oversized_code_rejected_without_spawning(self):
        result = CodeExecutor().execute_code('x = 1' * (MAX_CODE_LENGTH // 4))
        self.assertEqual(result['status'], 'error')
        self.assertIn('too long', result['error'])
        self.assertEqual(result['execution_time'], 0)

    def test_invalid_mode_rejected(self):
        result = CodeExecutor().execute_code('print(1)', mode='unrestricted')
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid execution mode', result['error'])

    def test_stdin_input_reaches_program(self):
        result = CodeExecutor().execute_code(
            'name = input()\nprint(f"hello {name}")', stdin_input='world')
        self.assertEqual(result['status'], 'success')
        self.assertIn('hello world', result['output'])

    def test_convenience_wrapper(self):
        result = execute_python_code('print(21 * 2)')
        self.assertEqual(result['status'], 'success')
        self.assertIn('42', result['output'])


class ExecutorDockerBackendTests(SimpleTestCase):
    """Docker transport branches, fully mocked — no docker CLI involved."""

    def _completed(self, stdout='', stderr='', returncode=0):
        completed = mock.Mock()
        completed.stdout = stdout
        completed.stderr = stderr
        completed.returncode = returncode
        return completed

    def test_docker_cli_missing_reports_clear_error(self):
        executor = CodeExecutor(backend='docker')
        with mock.patch('apps.code_runner.executor._docker_available',
                        return_value=False):
            result = executor.execute_code('print(1)')
        self.assertEqual(result['status'], 'error')
        self.assertIn('Docker backend configured but the docker CLI was not found',
                      result['error'])

    def test_docker_container_failure_reports_stderr(self):
        executor = CodeExecutor(backend='docker')
        completed = self._completed(
            stderr='docker: image not found\nerror detail',
            returncode=125)
        with mock.patch('apps.code_runner.executor._docker_available',
                        return_value=True), \
             mock.patch.object(executor, '_spawn_docker',
                               return_value=completed):
            result = executor.execute_code('print(1)')
        self.assertEqual(result['status'], 'error')
        self.assertIn('is the sandbox image built', result['error'])
        self.assertIn('error detail', result['error'])

    def test_docker_timeout_becomes_clean_error(self):
        executor = CodeExecutor(backend='docker', timeout=1)
        with mock.patch('apps.code_runner.executor._docker_available',
                        return_value=True), \
             mock.patch.object(executor, '_spawn_docker',
                               side_effect=TimeoutError('Execution timed out')):
            result = executor.execute_code('print(1)')
        self.assertEqual(result['status'], 'error')
        self.assertIn('timed out', result['error'])

    def test_force_docker_mode_overrides_backend(self):
        executor = CodeExecutor(backend='subprocess')
        completed = self._completed(stdout='__SANDBOX_RESULT__{"status": "success", "output": "ok"}')
        with mock.patch.object(executor, '_spawn_docker',
                               return_value=completed) as spawn:
            result = executor.execute_code('print(1)', mode='docker')
        self.assertTrue(spawn.called)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['output'], 'ok')
        self.assertEqual(executor.backend, 'subprocess')  # restored

    def test_malformed_sentinel_falls_back_to_stderr(self):
        executor = CodeExecutor()
        completed = self._completed(stdout='__SANDBOX_RESULT__{not json',
                                    stderr='traceback line')
        with mock.patch.object(executor, '_spawn_subprocess',
                               return_value=completed):
            result = executor.execute_code('print(1)')
        self.assertEqual(result['status'], 'error')
        self.assertIn('执行环境异常', result['error'])

    def test_missing_sentinel_with_empty_stderr(self):
        executor = CodeExecutor()
        completed = self._completed(stdout='random output', returncode=1)
        with mock.patch.object(executor, '_spawn_subprocess',
                               return_value=completed):
            result = executor.execute_code('print(1)')
        self.assertEqual(result['status'], 'error')
        self.assertIn('unknown sandbox failure', result['error'])


class ExecutorTestModeTests(SimpleTestCase):
    def test_dict_form_test_cases_still_supported(self):
        """Legacy {'tests': [...]} shape (see root smoke scripts of old)."""
        executor = CodeExecutor(timeout=10)
        result = executor.execute_with_tests(
            'def add(a, b):\n    return a + b',
            {'tests': [{'input': 'add(1, 2)', 'expected': 3}]})
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['total_tests'], 1)
        self.assertEqual(result['passed_tests'], 1)
        self.assertIn('Passed 1/1', result['message'])

    def test_timeout_raises(self):
        executor = CodeExecutor(timeout=1)
        with self.assertRaises(TimeoutError):
            executor.execute_with_tests(
                'while True: pass',
                [{'input': '1+1', 'expected': 2}], timeout=1)
