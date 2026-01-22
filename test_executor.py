
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from apps.code_runner.executor import CodeExecutor

def test_executor():
    executor = CodeExecutor()
    
    # 1. Test successful code
    print("\n--- Test 1: Successful Code ---")
    code = """
def add(a, b):
    print(f"Adding {a} + {b}")
    return a + b
"""
    test_cases = {
        'tests': [
            {'input': 'add(1, 2)', 'expected': 3},
            {'input': 'add(-1, 5)', 'expected': 4}
        ]
    }
    
    result = executor.execute_with_tests(code, test_cases)
    print(f"Status: {result['status']}")
    print(f"Passed: {result['passed_tests']}/{result['total_tests']}")
    print(f"Output:\n{result['output']}")
    print(f"Test Results: {result['test_results']}")

    # 2. Test incorrect code
    print("\n--- Test 2: Incorrect Code ---")
    code_wrong = """
def add(a, b):
    return a - b # Wrong implementation
"""
    result_wrong = executor.execute_with_tests(code_wrong, test_cases)
    print(f"Status: {result_wrong['status']}")
    print(f"Passed: {result_wrong['passed_tests']}/{result_wrong['total_tests']}")
    
    # 3. Test syntax error
    print("\n--- Test 3: Syntax Error ---")
    code_error = """
def add(a, b) # Missing colon
    return a + b
"""
    result_error = executor.execute_with_tests(code_error, test_cases)
    print(f"Status: {result_error['status']}")
    print(f"Error: {result_error['error']}")

    # 4. Test prohibited code
    print("\n--- Test 4: Prohibited Code ---")
    code_bad = """
import os
def add(a, b):
    return a + b
"""
    result_bad = executor.execute_with_tests(code_bad, test_cases)
    print(f"Status: {result_bad['status']}")
    print(f"Error: {result_bad['error']}")

if __name__ == "__main__":
    test_executor()
