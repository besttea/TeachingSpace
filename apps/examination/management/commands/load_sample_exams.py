from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.examination.models import (
    Exam, Question, MultipleChoiceQuestion, CodeQuestion,
    EssayQuestion, TrueFalseQuestion
)

User = get_user_model()


class Command(BaseCommand):
    help = '加载示例考试数据'

    def handle(self, *args, **options):
        self.stdout.write('开始创建示例考试...')

        # Get or create an instructor user
        instructor, created = User.objects.get_or_create(
            username='instructor',
            defaults={
                'email': 'instructor@example.com',
                'user_type': 'instructor',
                'first_name': '张',
                'last_name': '老师'
            }
        )
        if created:
            instructor.set_password('instructor123')
            instructor.save()
            self.stdout.write(self.style.SUCCESS(f'创建教师账号: {instructor.username}'))

        # Create Sample Exam 1: Python Basics
        exam1, created = Exam.objects.get_or_create(
            title='Python基础测试',
            defaults={
                'description': '测试Python基础知识，包括数据类型、控制结构和函数。',
                'duration_minutes': 30,
                'passing_score': 60,
                'max_attempts': 3,
                'is_published': True,
                'randomize_questions': True,
                'show_results_immediately': True,
                'created_by': instructor
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'创建考试: {exam1.title}'))

            # Question 1: Multiple Choice
            q1 = Question.objects.create(
                exam=exam1,
                question_type='multiple_choice',
                question_text='以下哪个不是Python的基本数据类型？',
                points=10,
                order=1
            )
            MultipleChoiceQuestion.objects.create(
                question=q1,
                options={
                    'A': 'int (整数)',
                    'B': 'float (浮点数)',
                    'C': 'char (字符)',
                    'D': 'str (字符串)'
                },
                correct_answer='C',
                explanation='Python没有char类型，字符在Python中是长度为1的字符串。'
            )

            # Question 2: True/False
            q2 = Question.objects.create(
                exam=exam1,
                question_type='true_false',
                question_text='Python中的列表(list)是可变的，而元组(tuple)是不可变的。',
                points=10,
                order=2
            )
            TrueFalseQuestion.objects.create(
                question=q2,
                correct_answer=True,
                explanation='列表是可变的，可以修改、添加或删除元素。元组是不可变的，创建后不能修改。'
            )

            # Question 3: Code Question
            q3 = Question.objects.create(
                exam=exam1,
                question_type='code',
                question_text='编写一个函数，判断一个数字是否为质数。函数名为is_prime，接受一个整数n作为参数，返回True或False。',
                points=20,
                order=3
            )
            CodeQuestion.objects.create(
                question=q3,
                starter_code='''def is_prime(n):
    """判断n是否为质数"""
    # 在这里编写你的代码
    pass
''',
                test_cases=[
                    {'input': 'is_prime(2)', 'expected_output': 'True', 'is_hidden': False},
                    {'input': 'is_prime(17)', 'expected_output': 'True', 'is_hidden': False},
                    {'input': 'is_prime(1)', 'expected_output': 'False', 'is_hidden': False},
                    {'input': 'is_prime(4)', 'expected_output': 'False', 'is_hidden': False},
                    {'input': 'is_prime(97)', 'expected_output': 'True', 'is_hidden': True},
                ],
                solution_code='''def is_prime(n):
    """判断n是否为质数"""
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True
''',
                explanation='质数是大于1的自然数，除了1和它自身外，不能被其他自然数整除。'
            )

            # Question 4: Multiple Choice
            q4 = Question.objects.create(
                exam=exam1,
                question_type='multiple_choice',
                question_text='以下哪个函数可以获取列表的长度？',
                points=10,
                order=4
            )
            MultipleChoiceQuestion.objects.create(
                question=q4,
                options={
                    'A': 'length()',
                    'B': 'len()',
                    'C': 'size()',
                    'D': 'count()'
                },
                correct_answer='B',
                explanation='len()函数用于获取序列(包括列表、字符串、元组等)的长度。'
            )

            # Question 5: Essay Question
            q5 = Question.objects.create(
                exam=exam1,
                question_type='essay',
                question_text='请简要说明Python中列表(list)和字典(dict)的区别，并各举一个使用场景的例子。',
                points=20,
                order=5
            )
            EssayQuestion.objects.create(
                question=q5,
                word_limit=200,
                rubric='''
评分标准:
- 正确说明列表和字典的区别 (10分)
- 举例恰当、具体 (5分)
- 表述清晰、逻辑性强 (5分)
''',
                sample_answer='''列表是有序的元素集合，使用索引访问；字典是无序的键值对集合，使用键访问。

列表使用场景: 存储一组学生的成绩，如 scores = [85, 90, 78, 92]，按顺序记录。

字典使用场景: 存储学生信息，如 student = {"name": "张三", "age": 20, "score": 85}，通过键快速访问特定信息。'''
            )

            # Question 6: True/False
            q6 = Question.objects.create(
                exam=exam1,
                question_type='true_false',
                question_text='Python使用缩进来表示代码块，而不是使用花括号{}。',
                points=10,
                order=6
            )
            TrueFalseQuestion.objects.create(
                question=q6,
                correct_answer=True,
                explanation='Python使用缩进来表示代码块的层次结构，这是Python的一个重要特征。'
            )

            # Question 7: Code Question
            q7 = Question.objects.create(
                exam=exam1,
                question_type='code',
                question_text='编写一个函数reverse_string，接受一个字符串参数，返回该字符串的反转结果。',
                points=20,
                order=7
            )
            CodeQuestion.objects.create(
                question=q7,
                starter_code='''def reverse_string(s):
    """反转字符串"""
    # 在这里编写你的代码
    pass
''',
                test_cases=[
                    {'input': 'reverse_string("hello")', 'expected_output': '"olleh"', 'is_hidden': False},
                    {'input': 'reverse_string("Python")', 'expected_output': '"nohtyP"', 'is_hidden': False},
                    {'input': 'reverse_string("")', 'expected_output': '""', 'is_hidden': False},
                ],
                solution_code='''def reverse_string(s):
    """反转字符串"""
    return s[::-1]
''',
                explanation='可以使用切片[::-1]来反转字符串，这是Python中最简洁的方法。'
            )

            self.stdout.write(self.style.SUCCESS(f'为 {exam1.title} 创建了 {exam1.questions.count()} 道题目'))

        # Create Sample Exam 2: Data Structures
        exam2, created = Exam.objects.get_or_create(
            title='Python数据结构进阶',
            defaults={
                'description': '测试对Python数据结构的深入理解，包括列表、字典、集合等。',
                'duration_minutes': 45,
                'passing_score': 70,
                'max_attempts': 2,
                'is_published': True,
                'randomize_questions': True,
                'show_results_immediately': True,
                'created_by': instructor
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'创建考试: {exam2.title}'))

            # Question 1: Multiple Choice
            q1 = Question.objects.create(
                exam=exam2,
                question_type='multiple_choice',
                question_text='以下哪个数据结构不允许存在重复元素？',
                points=10,
                order=1
            )
            MultipleChoiceQuestion.objects.create(
                question=q1,
                options={
                    'A': 'list (列表)',
                    'B': 'tuple (元组)',
                    'C': 'set (集合)',
                    'D': 'dict (字典)'
                },
                correct_answer='C',
                explanation='集合(set)是无序的、不允许重复元素的数据结构。'
            )

            # Question 2: Code Question
            q2 = Question.objects.create(
                exam=exam2,
                question_type='code',
                question_text='编写一个函数find_duplicates，接受一个列表参数，返回列表中所有重复出现的元素(作为列表)。',
                points=25,
                order=2
            )
            CodeQuestion.objects.create(
                question=q2,
                starter_code='''def find_duplicates(lst):
    """找出列表中重复的元素"""
    # 在这里编写你的代码
    pass
''',
                test_cases=[
                    {'input': 'find_duplicates([1, 2, 3, 2, 4, 3])', 'expected_output': '[2, 3]', 'is_hidden': False},
                    {'input': 'find_duplicates([1, 1, 1, 1])', 'expected_output': '[1]', 'is_hidden': False},
                    {'input': 'find_duplicates([1, 2, 3, 4])', 'expected_output': '[]', 'is_hidden': False},
                ],
                solution_code='''def find_duplicates(lst):
    """找出列表中重复的元素"""
    seen = set()
    duplicates = set()
    for item in lst:
        if item in seen:
            duplicates.add(item)
        else:
            seen.add(item)
    return list(duplicates)
''',
                explanation='使用两个集合来跟踪已见过的元素和重复的元素。'
            )

            # Question 3: Essay Question
            q3 = Question.objects.create(
                exam=exam2,
                question_type='essay',
                question_text='请解释Python中列表推导式(list comprehension)的优势，并举例说明。',
                points=15,
                order=3
            )
            EssayQuestion.objects.create(
                question=q3,
                word_limit=150,
                rubric='正确解释优势(7分)，举例恰当(5分)，表达清晰(3分)',
                sample_answer='''列表推导式的优势包括：1)代码更简洁、可读性更强；2)执行效率更高。

例如，生成1到10的平方：
传统方法：
squares = []
for i in range(1, 11):
    squares.append(i**2)

列表推导式：
squares = [i**2 for i in range(1, 11)]

列表推导式只用一行代码就完成了同样的功能。'''
            )

            self.stdout.write(self.style.SUCCESS(f'为 {exam2.title} 创建了 {exam2.questions.count()} 道题目'))

        self.stdout.write(self.style.SUCCESS('示例考试数据创建完成!'))
        self.stdout.write(f'考试总数: {Exam.objects.count()}')
        self.stdout.write(f'题目总数: {Question.objects.count()}')
        self.stdout.write('教师账号: instructor / instructor123')
