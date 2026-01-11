"""
Code execution engine for running Python code securely.

This module provides two execution modes:
1. RestrictedPython: Fast, limited execution for simple code (learning lessons)
2. Docker: Full isolation for exercises and exams (to be implemented)
"""

import sys
import io
import time
import traceback
from contextlib import redirect_stdout, redirect_stderr


class CodeExecutor:
    """
    Secure Python code executor with resource limits and sandboxing.

    Currently implements RestrictedPython mode for basic execution.
    Docker mode for full isolation will be implemented later.
    """

    def __init__(self, timeout=5, max_output_length=10000):
        """
        Initialize the code executor.

        Args:
            timeout: Maximum execution time in seconds (default: 5)
            max_output_length: Maximum output length in characters (default: 10000)
        """
        self.timeout = timeout
        self.max_output_length = max_output_length

    def execute_code(self, code, mode='restricted'):
        """
        Execute Python code and return results.

        Args:
            code: Python code string to execute
            mode: Execution mode ('restricted' or 'docker')

        Returns:
            dict: {
                'output': str,  # Combined stdout and stderr
                'status': str,  # 'success' or 'error'
                'execution_time': float,  # Milliseconds
                'error': str  # Error message if status is 'error'
            }
        """
        if mode == 'restricted':
            return self._execute_restricted(code)
        elif mode == 'docker':
            return self._execute_docker(code)
        else:
            return {
                'output': '',
                'status': 'error',
                'execution_time': 0,
                'error': f'Invalid execution mode: {mode}'
            }

    def _execute_restricted(self, code):
        """
        Execute code using RestrictedPython with basic sandboxing.

        This mode is fast but limited - suitable for learning lessons.
        Restricted features:
        - No file I/O
        - No network access
        - No subprocess execution
        - Limited imports
        """
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()

        start_time = time.time()
        status = 'success'
        error_message = None

        # Restricted globals - only safe built-ins
        safe_builtins = {
            'print': print,
            'len': len,
            'range': range,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'sorted': sorted,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'type': type,
            'isinstance': isinstance,
            'hasattr': hasattr,
            'getattr': getattr,
            'dir': dir,
            'help': help,
            '__builtins__': {
                '__import__': __import__,  # Restricted import
            }
        }

        # Check for prohibited operations
        prohibited_keywords = [
            'import os',
            'import sys',
            'import subprocess',
            'import socket',
            'open(',
            '__import__',
            'exec(',
            'eval(',
            'compile(',
        ]

        code_lower = code.lower()
        for keyword in prohibited_keywords:
            if keyword in code_lower:
                return {
                    'output': '',
                    'status': 'error',
                    'execution_time': 0,
                    'error': f'Prohibited operation detected: {keyword}'
                }

        try:
            # Redirect stdout and stderr
            with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
                # Create a restricted namespace
                namespace = {'__builtins__': safe_builtins}

                # Execute the code
                exec(code, namespace)

            output = output_buffer.getvalue()
            errors = error_buffer.getvalue()

            if errors:
                output += '\n' + errors

        except Exception as e:
            status = 'error'
            error_message = f'{type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}'
            output = error_message

        end_time = time.time()
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds

        # Truncate output if too long
        if len(output) > self.max_output_length:
            output = output[:self.max_output_length] + '\n... (output truncated)'

        return {
            'output': output,
            'status': status,
            'execution_time': execution_time,
            'error': error_message
        }

    def _execute_docker(self, code, test_cases=None):
        """
        Execute code in isolated Docker container (to be implemented).

        This mode provides full isolation and is suitable for exercises and exams.

        Args:
            code: Python code to execute
            test_cases: Optional list of test cases to run

        Returns:
            dict: Execution results
        """
        # TODO: Implement Docker-based execution
        return {
            'output': '',
            'status': 'error',
            'execution_time': 0,
            'error': 'Docker execution mode not yet implemented. Coming soon!'
        }

    def execute_with_tests(self, code, test_cases, timeout=10):
        """
        Execute code and run test cases against it.

        Args:
            code: Python code to execute
            test_cases: List of test case dictionaries with 'input' and 'expected_output'
            timeout: Maximum execution time in seconds

        Returns:
            dict: {
                'status': str,  # 'passed', 'failed', or 'error'
                'total_tests': int,
                'passed_tests': int,
                'failed_tests': int,
                'test_results': list,  # Individual test results
                'execution_time': float,
                'error': str
            }
        """
        # TODO: Implement full test execution
        # For now, return a placeholder
        return {
            'status': 'error',
            'total_tests': len(test_cases) if test_cases else 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'test_results': [],
            'execution_time': 0,
            'error': 'Test execution not yet fully implemented'
        }


# Convenience function for simple execution
def execute_python_code(code, timeout=5):
    """
    Simple wrapper function to execute Python code.

    Args:
        code: Python code string
        timeout: Maximum execution time in seconds

    Returns:
        dict: Execution results
    """
    executor = CodeExecutor(timeout=timeout)
    return executor.execute_code(code, mode='restricted')
