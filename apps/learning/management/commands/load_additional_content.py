
"""
Management command to load additional content for the Python course.
"""

from django.core.management.base import BaseCommand
from apps.accounts.models import User
from apps.learning.models import Course, Chapter, Lesson, Cell

class Command(BaseCommand):
    help = 'Load additional content (Chapters 1.2, 1.3, and 2.1) for the Python course'

    def handle(self, *args, **options):
        # Get instructor
        instructor = User.objects.filter(username='admin').first()
        if not instructor:
            self.stdout.write(self.style.ERROR('Instructor "admin" not found. Please run load_notebook_data first.'))
            return

        # Get Course
        course = Course.objects.filter(title="Python编程基础").first()
        if not course:
            self.stdout.write(self.style.ERROR('Course "Python编程基础" not found. Please run load_notebook_data first.'))
            return

        # --- Chapter 1: Continue ---
        chapter1 = Chapter.objects.get(course=course, order=1)

        # Lesson 2: Control Flow
        self._create_lesson_control_flow(chapter1, instructor)

        # Lesson 3: Functions
        self._create_lesson_functions(chapter1, instructor)

        # --- Chapter 2: Advanced Topics ---
        chapter2, created = Chapter.objects.get_or_create(
            course=course,
            title="第2章 面向对象编程",
            defaults={
                'description': '深入理解Python的类与对象体系',
                'order': 2,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created chapter: {chapter2.title}'))

        # Lesson 1 (Chapter 2): OOP Basics
        self._create_lesson_oop(chapter2, instructor)

    def _create_lesson_control_flow(self, chapter, instructor):
        lesson, created = Lesson.objects.get_or_create(
            chapter=chapter,
            title="第二讲 流程控制",
            defaults={
                'description': '掌握条件判断与循环结构',
                'order': 2,
                'status': 'published'
            }
        )
        if not created:
            lesson.cells.all().delete()
            self.stdout.write(f'Updating lesson: {lesson.title}')
        else:
            self.stdout.write(self.style.SUCCESS(f'Created lesson: {lesson.title}'))

        cells_data = [
            ('text', '# Python 流程控制\n\n在本节中，我们将学习如何控制程序的执行流程，包括条件判断和循环。'),
            ('text', '## 1. 条件判断 (If Statements)\n\n`if` 语句允许程序根据条件执行不同的代码块。'),
            ('code', 'age = 20\n\nif age >= 18:\n    print("成年人")\nelse:\n    print("未成年人")'),
            ('text', '## 2. For 循环\n\n`for` 循环用于遍历序列（如列表、元组、字符串）。'),
            ('code', 'fruits = ["apple", "banana", "cherry"]\n\nfor fruit in fruits:\n    print(f"I like {fruit}")'),
            ('text', '## 3. While 循环\n\n`while` 循环在条件为真时重复执行代码块。'),
            ('code', 'count = 0\nwhile count < 5:\n    print(count)\n    count += 1'),
            ('text', '### 练习\n尝试编写一个循环，计算1到100的所有整数之和。'),
            ('code', '# 在这里编写你的代码\ntotal = 0\nfor i in range(1, 101):\n    total += i\nprint(total)')
        ]
        self._create_cells(lesson, cells_data, instructor)

    def _create_lesson_functions(self, chapter, instructor):
        lesson, created = Lesson.objects.get_or_create(
            chapter=chapter,
            title="第三讲 函数",
            defaults={
                'description': '学习如何定义和使用函数',
                'order': 3,
                'status': 'published'
            }
        )
        if not created:
            lesson.cells.all().delete()
            self.stdout.write(f'Updating lesson: {lesson.title}')
        else:
            self.stdout.write(self.style.SUCCESS(f'Created lesson: {lesson.title}'))

        cells_data = [
            ('text', '# Python 函数\n\n函数是组织好的、可重复使用的代码段。'),
            ('text', '## 1. 定义函数\n\n使用 `def` 关键字定义函数。'),
            ('code', 'def greet(name):\n    return f"Hello, {name}!"\n\nprint(greet("Alice"))'),
            ('text', '## 2. 参数与返回值\n\n函数可以接收多个参数，并返回一个值。'),
            ('code', 'def add(a, b):\n    return a + b\n\nresult = add(5, 3)\nprint(result)'),
            ('text', '## 3. 默认参数\n\n可以为参数指定默认值。'),
            ('code', 'def power(base, exponent=2):\n    return base ** exponent\n\nprint(power(3))    # 3^2 = 9\nprint(power(3, 3)) # 3^3 = 27')
        ]
        self._create_cells(lesson, cells_data, instructor)

    def _create_lesson_oop(self, chapter, instructor):
        lesson, created = Lesson.objects.get_or_create(
            chapter=chapter,
            title="第一讲 类与对象",
            defaults={
                'description': '面向对象编程基础',
                'order': 1,
                'status': 'published'
            }
        )
        if not created:
            lesson.cells.all().delete()
            self.stdout.write(f'Updating lesson: {lesson.title}')
        else:
            self.stdout.write(self.style.SUCCESS(f'Created lesson: {lesson.title}'))

        cells_data = [
            ('text', '# 面向对象编程 (OOP)\n\nPython 是一门面向对象的语言。几乎所有的东西都是对象。'),
            ('text', '## 1. 定义类 (Class)\n\n类是对象的蓝图。'),
            ('code', 'class Dog:\n    def __init__(self, name):\n        self.name = name\n\n    def bark(self):\n        return f"{self.name} says Woof!"\n\n# 创建对象\nmy_dog = Dog("Buddy")\nprint(my_dog.bark())'),
            ('text', '## 2. 继承\n\n子类可以继承父类的属性和方法。'),
            ('code', 'class Animal:\n    def speak(self):\n        pass\n\nclass Cat(Animal):\n    def speak(self):\n        return "Meow"\n\ncat = Cat()\nprint(cat.speak())')
        ]
        self._create_cells(lesson, cells_data, instructor)

    def _create_cells(self, lesson, cells_data, instructor):
        for idx, (ctype, content) in enumerate(cells_data):
            cell_data = {}
            if ctype == 'text':
                cell_data['markdown'] = content
            elif ctype == 'code':
                cell_data['source'] = content
                cell_data['language'] = 'python'

            Cell.objects.create(
                lesson=lesson,
                cell_type=ctype,
                order=idx,
                data=cell_data,
                created_by=instructor
            )
