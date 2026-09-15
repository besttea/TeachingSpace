"""Regression tests for the sandboxed code executor.

Covers the P0-1/P0-2 fixes: subprocess isolation, enforced timeouts, and
blocked escape vectors (imports, dunder gadget chains, file access).
"""

import time

from django.test import SimpleTestCase

from .executor import CodeExecutor


class CodeExecutorSandboxTests(SimpleTestCase):
    def setUp(self):
        self.executor = CodeExecutor(timeout=5)

    def test_simple_execution(self):
        result = self.executor.execute_code("print('hello', 1 + 1)")
        self.assertEqual(result['status'], 'success')
        self.assertIn('hello 2', result['output'])

    def test_whitelisted_import_works(self):
        result = self.executor.execute_code('import math\nprint(math.sqrt(16))')
        self.assertEqual(result['status'], 'success')
        self.assertIn('4.0', result['output'])

    def test_import_os_blocked(self):
        result = self.executor.execute_code('import os\nprint(os.getcwd())')
        self.assertEqual(result['status'], 'error')
        self.assertIn('not allowed', result['error'])

    def test_from_import_blocked(self):
        result = self.executor.execute_code('from os import system\nsystem("echo pwned")')
        self.assertEqual(result['status'], 'error')

    def test_dunder_gadget_chain_blocked(self):
        # The classic __class__.__mro__[1].__subclasses__() escape
        result = self.executor.execute_code("print(().__class__.__mro__)")
        self.assertEqual(result['status'], 'error')
        self.assertIn('private attribute', result['error'])

    def test_open_blocked(self):
        result = self.executor.execute_code("open('manage.py', 'r').read()")
        self.assertEqual(result['status'], 'error')

    def test_builtins_introspection_blocked(self):
        result = self.executor.execute_code("print(len.__self__.__dict__)")
        self.assertEqual(result['status'], 'error')

    def test_classes_and_exceptions_still_work(self):
        code = (
            "class Foo:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "    def double(self):\n"
            "        return self.x * 2\n"
            "f = Foo()\n"
            "try:\n"
            "    raise ValueError('bad')\n"
            "except ValueError as e:\n"
            "    print('caught', e)\n"
            "print(f.double())"
        )
        result = self.executor.execute_code(code)
        self.assertEqual(result['status'], 'success')
        self.assertIn('caught bad', result['output'])
        self.assertIn('2', result['output'])

    def test_timeout_enforced(self):
        start = time.time()
        result = self.executor.execute_code('while True: pass')
        elapsed = time.time() - start
        self.assertEqual(result['status'], 'error')
        self.assertIn('timed out', result['error'])
        self.assertLess(elapsed, 15)  # generous bound; real timeout is 5s

    def test_no_server_paths_in_errors(self):
        result = self.executor.execute_code('print(1/0)')
        self.assertEqual(result['status'], 'error')
        self.assertIn('ZeroDivisionError', result['error'])
        self.assertNotIn('TeachingSpace', result['error'])


class CodeExecutorTestModesTests(SimpleTestCase):
    def test_stdin_stdout_tests(self):
        executor = CodeExecutor()
        result = executor.execute_with_tests(
            'name = input()\nprint("Hello, " + name + "!")',
            [
                {'input': 'World', 'expected_output': 'Hello, World!'},
                {'input': 'X', 'expected_output': 'Hello, X!'},
            ],
            timeout=10,
        )
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['passed_tests'], 2)
        self.assertEqual(result['total_tests'], 2)

    def test_stdin_tests_can_fail(self):
        executor = CodeExecutor()
        result = executor.execute_with_tests(
            'print("wrong")',
            [{'input': '', 'expected_output': 'right'}],
            timeout=10,
        )
        self.assertEqual(result['status'], 'error')  # 0 passed
        self.assertEqual(result['passed_tests'], 0)
        self.assertEqual(result['failed_tests'], 1)

    def test_function_tests(self):
        executor = CodeExecutor()
        result = executor.execute_with_tests(
            'def add(a, b):\n    return a + b',
            [
                {'input': 'add(2, 3)', 'expected': 5},
                {'input': 'add(1, 1)', 'expected': 2},
            ],
            timeout=10,
        )
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['passed_tests'], 2)

    def test_result_keys_match_callers(self):
        """training/models.grade() and examination/views read these exact keys."""
        executor = CodeExecutor()
        result = executor.execute_with_tests(
            'print("hi")',
            [{'input': '', 'expected_output': 'hi'}],
            timeout=10,
        )
        for key in ('status', 'total_tests', 'passed_tests', 'failed_tests',
                    'test_results', 'execution_time', 'error', 'output', 'message'):
            self.assertIn(key, result)
