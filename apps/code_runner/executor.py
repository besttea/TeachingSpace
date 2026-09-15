"""
Code execution engine for running student Python code.

Security model: student code NEVER runs inside the Django process. Every
execution happens in a fresh ``python -I`` subprocess with:

- a hard wall-clock timeout enforced by the parent (kills the subprocess),
- a strict builtins whitelist (no ``__import__`` except a small allowlist,
  no ``open``/``eval``/``exec``/``compile``, no introspection helpers like
  ``type``/``getattr``/``dir``),
- output captured and truncated,
- (if installed) RestrictedPython bytecode compilation as an additional
  layer against ``__class__``-style gadget chains.

Limitations (documented, not hidden): the subprocess is isolated from the
server process but not from the OS — it runs as the same OS user with
network access. Full OS-level isolation requires the Docker mode
(``mode='docker'``), which is still a stub.
"""

import io
import json
import os
import subprocess
import sys
import time

#: Hard cap on submitted code length (sanity guard for the JSON pipe).
MAX_CODE_LENGTH = 100_000
#: Sentinel marking the result JSON on the sandbox subprocess stdout.
_SENTINEL = '__SANDBOX_RESULT__'

#: Modules students may import inside the sandbox.
_ALLOWED_IMPORTS = frozenset({
    'math', 'random', 'json', 're', 'collections', 'itertools',
    'functools', 'heapq', 'statistics', 'string', 'datetime', 'decimal',
    'fractions', 'copy', 'bisect', 'enum', 'typing', 'calendar',
})

#: Runner script executed inside the subprocess (stdlib only).
_SANDBOX_RUNNER = r'''
import ast
import io
import json
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

SENTINEL = '__SANDBOX_RESULT__'
ALLOWED_IMPORTS = {
    'math', 'random', 'json', 're', 'collections', 'itertools',
    'functools', 'heapq', 'statistics', 'string', 'datetime', 'decimal',
    'fractions', 'copy', 'bisect', 'enum', 'typing', 'calendar',
}

_orig_import = __import__

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split('.')[0]
    if root not in ALLOWED_IMPORTS:
        raise ImportError("import of %r is not allowed in this sandbox" % name)
    return _orig_import(name, globals, locals, fromlist, level)

SAFE_BUILTINS = {
    'print': print, 'input': input,
    'len': len, 'range': range, 'iter': iter, 'next': next, 'reversed': reversed,
    'enumerate': enumerate, 'zip': zip, 'map': map, 'filter': filter,
    'str': str, 'int': int, 'float': float, 'bool': bool, 'complex': complex,
    'list': list, 'dict': dict, 'tuple': tuple, 'set': set, 'frozenset': frozenset,
    'abs': abs, 'min': min, 'max': max, 'sum': sum, 'round': round, 'pow': pow,
    'divmod': divmod, 'sorted': sorted, 'all': all, 'any': any,
    'chr': chr, 'ord': ord, 'repr': repr, 'format': format,
    'isinstance': isinstance, 'issubclass': issubclass,
    '__build_class__': __build_class__,
    'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError,
    'KeyError': KeyError, 'IndexError': IndexError, 'StopIteration': StopIteration,
    '__import__': _safe_import,
    '__name__': '__main__',
}

# Optional RestrictedPython hardening (used when the package is installed).
try:
    from RestrictedPython import compile_restricted
    from RestrictedPython.Guards import guarded_getattr, guarded_getitem, guarded_getiter
    HAVE_RESTRICTED = True
except ImportError:
    HAVE_RESTRICTED = False


def _check_no_private_attrs(tree):
    """Reject attribute access to names starting with '_'.

    Blocks the classic ``().__class__.__mro__[1].__subclasses__()`` gadget
    chains without RestrictedPython. Student code rarely needs private
    attributes; the error message explains the rule.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
            raise SyntaxError(
                "access to private attribute %r is not allowed in this sandbox" % node.attr)


def _compile(source):
    if HAVE_RESTRICTED:
        try:
            code, errors, _warnings, _used = compile_restricted(
                source, filename='<student-code>',
                policy={'allowed_imports': sorted(ALLOWED_IMPORTS)},
            )
        except TypeError:  # older RestrictedPython signatures
            code, errors, _warnings, _used = compile_restricted(
                source, filename='<student-code>')
        if errors:
            raise SyntaxError('; '.join(errors))
        return code
    tree = ast.parse(source, '<student-code>')
    _check_no_private_attrs(tree)
    return compile(tree, '<student-code>', 'exec')

def _execute_source(source, stdin_lines=None):
    """Execute source with captured stdout/stderr. Returns (ns, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    ns = {'__builtins__': dict(SAFE_BUILTINS)}
    if HAVE_RESTRICTED:
        ns['_getattr_'] = guarded_getattr
        ns['_getitem_'] = guarded_getitem
        ns['_getiter_'] = guarded_getiter
        ns['_write_'] = lambda x: x
    if stdin_lines is not None:
        iterator = iter(stdin_lines)
        def mock_input(prompt=''):
            if prompt:
                out.write(str(prompt))
            try:
                return next(iterator)
            except StopIteration:
                raise EOFError('EOF when reading a line')
        ns['__builtins__']['input'] = mock_input

    code_obj = _compile(source)
    with redirect_stdout(out), redirect_stderr(err):
        exec(code_obj, ns)
    return ns, out.getvalue(), err.getvalue()

def _error_text(exc):
    """Exception message + last traceback line, without server file paths."""
    tb = traceback.format_exc().strip().splitlines()
    relevant = [tb[-1]] if tb else []
    return '%s: %s\n%s' % (type(exc).__name__, exc, '\n'.join(relevant))

def _run_simple(req):
    result = {'output': '', 'status': 'success', 'error': None}
    stdin_input = req.get('stdin_input', '')
    try:
        lines = stdin_input.splitlines() if stdin_input else None
        _ns, out, err = _execute_source(req['code'], stdin_lines=lines)
        result['output'] = out + ('\n' + err if err else '')
        if err:
            result['status'] = 'error'
            result['error'] = err.strip()
    except Exception as e:
        result['status'] = 'error'
        result['error'] = _error_text(e)
    return result

def _run_tests(req):
    tests = req['test_cases'] or []
    code = req['code']
    result = {
        'status': 'error', 'total_tests': len(tests),
        'passed_tests': 0, 'failed_tests': 0, 'test_results': [],
        'error': None, 'output': '', 'message': '',
    }
    if not tests:
        result['error'] = 'No test cases provided'
        return result

    first = tests[0]
    is_function_test = 'expected_output' not in first and 'expected' in first

    if is_function_test:
        try:
            ns, out, err = _execute_source(code)
            for test in tests:
                test_result = {
                    'input': test.get('input'), 'expected': test.get('expected'),
                    'actual': None, 'passed': False, 'error': None,
                    'description': test.get('description', ''),
                    'is_hidden': test.get('is_hidden', False),
                }
                try:
                    actual = eval(test.get('input'), ns)
                    test_result['actual'] = actual
                    if actual == test.get('expected'):
                        test_result['passed'] = True
                        result['passed_tests'] += 1
                    else:
                        result['failed_tests'] += 1
                except Exception as e:
                    test_result['error'] = str(e)
                    result['failed_tests'] += 1
                result['test_results'].append(test_result)
            result['output'] = out + ('\n' + err if err else '')
        except Exception as e:
            result['error'] = _error_text(e)
    else:
        for i, test in enumerate(tests):
            input_data = test.get('input', '')
            expected_output = str(test.get('expected_output', '')).strip()
            case = {
                'case_index': i, 'input': input_data,
                'expected': expected_output, 'actual': '', 'passed': False,
                'error': None, 'is_hidden': test.get('is_hidden', False),
                'description': test.get('description', ''),
            }
            try:
                lines = input_data.splitlines() if input_data else None
                _ns, out, err = _execute_source(code, stdin_lines=lines)
                case['actual'] = out.strip()
                if err.strip():
                    case['passed'] = False
                    case['error'] = err.strip()
                    result['failed_tests'] += 1
                elif case['actual'] == expected_output:
                    case['passed'] = True
                    result['passed_tests'] += 1
                else:
                    result['failed_tests'] += 1
                result['output'] += out
            except Exception as e:
                case['error'] = _error_text(e)
                result['failed_tests'] += 1
            result['test_results'].append(case)

    if result['error'] is None and result['failed_tests'] == 0 and result['passed_tests'] == result['total_tests']:
        result['status'] = 'passed'
    elif result['passed_tests'] > 0:
        result['status'] = 'failed'
    return result

def main():
    req = json.loads(sys.stdin.read())
    mode = req.get('mode', 'tests')
    max_output = int(req.get('max_output_length', 10000))
    if mode == 'code':
        result = _run_simple(req)
    else:
        result = _run_tests(req)
    for key in ('output',):
        if len(result.get(key) or '') > max_output:
            result[key] = result[key][:max_output] + '\n... (output truncated)'
    result['execution_time'] = 0
    sys.stdout.write(SENTINEL + json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
'''


class CodeExecutor:
    """
    Sandboxed Python code executor (subprocess isolation + timeouts).
    """

    def __init__(self, timeout=5, max_output_length=10000):
        """
        Args:
            timeout: Maximum execution time in seconds (default: 5)
            max_output_length: Maximum output length in characters (default: 10000)
        """
        self.timeout = timeout
        self.max_output_length = max_output_length

    def _spawn(self, request: dict, timeout: float):
        """Run one sandbox subprocess; return the parsed result dict."""
        if os.name == 'nt':
            kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW}
        else:
            kwargs = {}
        try:
            completed = subprocess.run(
                [sys.executable, '-I', '-c', _SANDBOX_RUNNER],
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True, text=True, timeout=timeout, **kwargs,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f'Execution timed out after {timeout} seconds')

        stdout = completed.stdout or ''
        if _SENTINEL in stdout:
            try:
                return json.loads(stdout.split(_SENTINEL, 1)[1])
            except json.JSONDecodeError:
                pass
        # The runner itself crashed — surface a sanitized error.
        stderr = (completed.stderr or '').strip().splitlines()
        return {
            'status': 'error',
            'error': '执行环境异常: ' + (stderr[-1] if stderr else 'unknown sandbox failure'),
            'output': '',
        }

    def execute_code(self, code, mode='restricted', stdin_input=''):
        """
        Execute Python code and return results.

        Returns:
            dict: {'output', 'status' ('success'|'error'), 'execution_time', 'error'}
        """
        if mode == 'docker':
            return self._execute_docker(code, stdin_input)
        if mode not in ('restricted',):
            return {
                'output': '',
                'status': 'error',
                'execution_time': 0,
                'error': f'Invalid execution mode: {mode}'
            }
        if len(code) > MAX_CODE_LENGTH:
            return {
                'output': '',
                'status': 'error',
                'execution_time': 0,
                'error': f'Code too long (max {MAX_CODE_LENGTH} characters)'
            }

        start_time = time.time()
        try:
            result = self._spawn({
                'mode': 'code',
                'code': code,
                'stdin_input': stdin_input,
                'max_output_length': self.max_output_length,
            }, timeout=self.timeout)
        except TimeoutError as e:
            result = {'status': 'error', 'error': str(e), 'output': ''}

        result['execution_time'] = int((time.time() - start_time) * 1000)
        return result

    def execute_with_tests(self, code, test_cases, timeout=10):
        """
        Execute code and run test cases against it.

        Supports two test formats:
        1. stdin/stdout based: {'input': '...', 'expected_output': '...'}
        2. Function-based: {'input': 'func(args)', 'expected': result}

        Returns dict with keys: status, total_tests, passed_tests,
        failed_tests, test_results, execution_time, error, output, message.

        Raises TimeoutError if execution exceeds the time limit.
        """
        tests = []
        if isinstance(test_cases, dict):
            tests = test_cases.get('tests', [])
        elif isinstance(test_cases, list):
            tests = test_cases

        start_time = time.time()
        result = self._spawn({
            'mode': 'tests',
            'code': code,
            'test_cases': tests,
            'max_output_length': self.max_output_length,
        }, timeout=timeout)

        result.setdefault('total_tests', len(tests))
        result.setdefault('passed_tests', 0)
        result.setdefault('failed_tests', 0)
        result.setdefault('test_results', [])
        result['execution_time'] = int((time.time() - start_time) * 1000)
        result['message'] = f'Passed {result["passed_tests"]}/{result["total_tests"]} tests'
        return result

    def _execute_docker(self, code, stdin_input='', test_cases=None):
        """
        Execute code in isolated Docker container (to be implemented).

        This mode provides full isolation and is suitable for exercises and exams.
        """
        return {
            'output': '',
            'status': 'error',
            'execution_time': 0,
            'error': 'Docker execution mode not yet implemented. Coming soon!'
        }


# Convenience function for simple execution
def execute_python_code(code, timeout=5):
    """
    Simple wrapper function to execute Python code.
    """
    executor = CodeExecutor(timeout=timeout)
    return executor.execute_code(code, mode='restricted')
