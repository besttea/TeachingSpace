"""
Management command to create sample exercises for the Training Class.
"""

from django.core.management.base import BaseCommand
from apps.accounts.models import User
from apps.training.models import Exercise, Hint


class Command(BaseCommand):
    help = 'Create sample exercises for the Training Class'

    def handle(self, *args, **options):
        # Get or create instructor
        instructor, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'user_type': 'instructor',
                'is_staff': True,
            }
        )

        # Exercise 1: Sum of two numbers
        exercise1, created = Exercise.objects.get_or_create(
            title="求两数之和",
            slug="sum-of-two-numbers",
            defaults={
                'description': '''编写一个函数 `add_numbers(a, b)`，返回两个数的和。

### 要求
- 函数接受两个参数 a 和 b
- 返回 a + b 的结果

### 示例
```python
add_numbers(3, 5)  # 应该返回 8
add_numbers(-1, 1)  # 应该返回 0
```
''',
                'difficulty': 'beginner',
                'points': 10,
                'starter_code': '''def add_numbers(a, b):
    # 在这里编写你的代码
    pass
''',
                'test_cases': {
                    'tests': [
                        {
                            'input': 'add_numbers(3, 5)',
                            'expected': 8,
                            'description': '测试正数相加'
                        },
                        {
                            'input': 'add_numbers(-1, 1)',
                            'expected': 0,
                            'description': '测试负数和正数相加'
                        },
                        {
                            'input': 'add_numbers(0, 0)',
                            'expected': 0,
                            'description': '测试零'
                        },
                    ]
                },
                'solution_code': '''def add_numbers(a, b):
    return a + b
''',
                'created_by': instructor,
            }
        )
        if created:
            # Add hints
            Hint.objects.create(
                exercise=exercise1,
                order=1,
                content="记住，Python中使用 `+` 运算符可以相加两个数字。",
                points_penalty=2
            )
            Hint.objects.create(
                exercise=exercise1,
                order=2,
                content="你只需要使用 `return a + b` 来返回结果。",
                points_penalty=3
            )
            self.stdout.write(self.style.SUCCESS(f'Created exercise: {exercise1.title}'))

        # Exercise 2: Check if number is even
        exercise2, created = Exercise.objects.get_or_create(
            title="判断奇偶数",
            slug="check-even-odd",
            defaults={
                'description': '''编写一个函数 `is_even(n)`，判断一个数是否为偶数。

### 要求
- 函数接受一个整数参数 n
- 如果 n 是偶数，返回 True
- 如果 n 是奇数，返回 False

### 示例
```python
is_even(4)   # 应该返回 True
is_even(7)   # 应该返回 False
is_even(0)   # 应该返回 True
```
''',
                'difficulty': 'beginner',
                'points': 15,
                'starter_code': '''def is_even(n):
    # 在这里编写你的代码
    pass
''',
                'test_cases': {
                    'tests': [
                        {
                            'input': 'is_even(4)',
                            'expected': True,
                            'description': '测试偶数'
                        },
                        {
                            'input': 'is_even(7)',
                            'expected': False,
                            'description': '测试奇数'
                        },
                        {
                            'input': 'is_even(0)',
                            'expected': True,
                            'description': '测试零'
                        },
                        {
                            'input': 'is_even(-2)',
                            'expected': True,
                            'description': '测试负偶数'
                        },
                    ]
                },
                'solution_code': '''def is_even(n):
    return n % 2 == 0
''',
                'created_by': instructor,
            }
        )
        if created:
            # Add hints
            Hint.objects.create(
                exercise=exercise2,
                order=1,
                content="使用模运算符 `%` 可以获得除法的余数。",
                points_penalty=3
            )
            Hint.objects.create(
                exercise=exercise2,
                order=2,
                content="偶数除以2的余数为0。可以使用 `n % 2 == 0` 来判断。",
                points_penalty=5
            )
            self.stdout.write(self.style.SUCCESS(f'Created exercise: {exercise2.title}'))

        # Exercise 3: Find maximum in list
        exercise3, created = Exercise.objects.get_or_create(
            title="找出列表中的最大值",
            slug="find-maximum",
            defaults={
                'description': '''编写一个函数 `find_max(numbers)`，返回列表中的最大值。

### 要求
- 函数接受一个数字列表参数 numbers
- 返回列表中的最大值
- 可以假设列表不为空

### 示例
```python
find_max([1, 5, 3, 9, 2])  # 应该返回 9
find_max([-1, -5, -3])     # 应该返回 -1
find_max([42])             # 应该返回 42
```
''',
                'difficulty': 'beginner',
                'points': 20,
                'starter_code': '''def find_max(numbers):
    # 在这里编写你的代码
    pass
''',
                'test_cases': {
                    'tests': [
                        {
                            'input': 'find_max([1, 5, 3, 9, 2])',
                            'expected': 9,
                            'description': '测试正整数列表'
                        },
                        {
                            'input': 'find_max([-1, -5, -3])',
                            'expected': -1,
                            'description': '测试负数列表'
                        },
                        {
                            'input': 'find_max([42])',
                            'expected': 42,
                            'description': '测试单元素列表'
                        },
                    ]
                },
                'solution_code': '''def find_max(numbers):
    return max(numbers)

# 或者使用循环：
# def find_max(numbers):
#     max_num = numbers[0]
#     for num in numbers:
#         if num > max_num:
#             max_num = num
#     return max_num
''',
                'created_by': instructor,
            }
        )
        if created:
            # Add hints
            Hint.objects.create(
                exercise=exercise3,
                order=1,
                content="Python有一个内置函数 `max()` 可以找到列表中的最大值。",
                points_penalty=5
            )
            Hint.objects.create(
                exercise=exercise3,
                order=2,
                content="如果想自己实现，可以先假设第一个元素是最大值，然后遍历列表更新最大值。",
                points_penalty=3
            )
            Hint.objects.create(
                exercise=exercise3,
                order=3,
                content="完整实现：初始化 max_num = numbers[0]，然后用 for 循环遍历列表，如果找到更大的值就更新 max_num。",
                points_penalty=7
            )
            self.stdout.write(self.style.SUCCESS(f'Created exercise: {exercise3.title}'))

        # Exercise 4: Reverse a string
        exercise4, created = Exercise.objects.get_or_create(
            title="字符串反转",
            slug="reverse-string",
            defaults={
                'description': '''编写一个函数 `reverse_string(text)`，返回反转后的字符串。

### 要求
- 函数接受一个字符串参数 text
- 返回反转后的字符串

### 示例
```python
reverse_string("hello")    # 应该返回 "olleh"
reverse_string("Python")   # 应该返回 "nohtyP"
reverse_string("12345")    # 应该返回 "54321"
```
''',
                'difficulty': 'beginner',
                'points': 15,
                'starter_code': '''def reverse_string(text):
    # 在这里编写你的代码
    pass
''',
                'test_cases': {
                    'tests': [
                        {
                            'input': 'reverse_string("hello")',
                            'expected': "olleh",
                            'description': '测试简单字符串'
                        },
                        {
                            'input': 'reverse_string("Python")',
                            'expected': "nohtyP",
                            'description': '测试大小写混合'
                        },
                        {
                            'input': 'reverse_string("12345")',
                            'expected': "54321",
                            'description': '测试数字字符串'
                        },
                        {
                            'input': 'reverse_string("")',
                            'expected': "",
                            'description': '测试空字符串'
                        },
                    ]
                },
                'solution_code': '''def reverse_string(text):
    return text[::-1]

# 或者使用 reversed() 函数：
# def reverse_string(text):
#     return ''.join(reversed(text))
''',
                'created_by': instructor,
            }
        )
        if created:
            # Add hints
            Hint.objects.create(
                exercise=exercise4,
                order=1,
                content="Python的切片功能非常强大，可以使用负步长来反转序列。",
                points_penalty=3
            )
            Hint.objects.create(
                exercise=exercise4,
                order=2,
                content="使用 `text[::-1]` 可以反转字符串。其中 `::` 表示完整切片，`-1` 表示步长为-1（反向）。",
                points_penalty=5
            )
            self.stdout.write(self.style.SUCCESS(f'Created exercise: {exercise4.title}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nSuccessfully created sample exercises!'
            f'\nTotal exercises: {Exercise.objects.count()}'
        ))
