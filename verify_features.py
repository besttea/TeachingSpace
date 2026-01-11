import os
import json
import django
from django.conf import settings
from unittest.mock import MagicMock, patch

# Setup Django environment if running standalone (though we'll use manage.py shell)
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
# django.setup()

from apps.learning.models import Course, Lesson, Cell
from apps.learning.cell_handlers import get_handler
from apps.ai_agents.learning_agent import LearningAgent

def verify_data():
    print("=== Verifying Imported Data ===")
    course_title = "Python Basic Data Structures"
    try:
        course = Course.objects.get(title=course_title)
        print(f"[PASS] Course found: {course.title}")
        
        lessons = Lesson.objects.filter(chapter__course=course)
        print(f"[PASS] Lessons count: {lessons.count()}")
        
        if lessons.count() > 0:
            lesson = lessons.first()
            cells = Cell.objects.filter(lesson=lesson)
            print(f"[PASS] Lesson '{lesson.title}' has {cells.count()} cells")
            
            # Check content of a markdown cell
            md_cell = cells.filter(cell_type='text').first()
            if md_cell:
                print(f"[PASS] Found Markdown Cell. Content snippet: {md_cell.data.get('markdown', '')[:50]}...")
            else:
                print("[WARN] No Markdown cell found in first lesson")
                
            # Check content of a code cell
            # Search in all lessons for a code cell
            code_cell = Cell.objects.filter(lesson__chapter__course=course, cell_type='code').first()
            if code_cell:
                print(f"[PASS] Found Code Cell. Source snippet: {code_cell.data.get('source', '')[:50]}...")
            else:
                print("[WARN] No Code cell found in course")
                
    except Course.DoesNotExist:
        print(f"[FAIL] Course '{course_title}' not found!")

def verify_handlers():
    print("\n=== Verifying Cell Handlers ===")
    
    # Test Text Handler
    text_handler = get_handler('text')
    valid_data = {'markdown': '# Hello'}
    processed = text_handler.process(valid_data)
    if 'rendered_html' in processed:
        print(f"[PASS] TextCellHandler generated HTML: {processed['rendered_html']}")
    else:
        print(f"[FAIL] TextCellHandler failed to generate HTML")
        
    # Test Code Handler
    code_handler = get_handler('code')
    code_data = {'source': 'print(1)'}
    processed_code = code_handler.process(code_data)
    if 'execution_count' in processed_code:
        print(f"[PASS] CodeCellHandler added execution_count: {processed_code['execution_count']}")
    else:
        print(f"[FAIL] CodeCellHandler failed to process data")

def verify_agent():
    print("\n=== Verifying Learning Agent (Mocked) ===")
    
    # Mock the anthropic client to avoid API errors
    with patch('anthropic.Anthropic') as MockAnthropic:
        # Setup mock response
        mock_client = MockAnthropic.return_value
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps({
            "cells": [
                {"type": "text", "content": "# Generated Lesson\n\nIntro..."},
                {"type": "code", "content": "print('AI Generated')"}
            ]
        }))]
        mock_client.messages.create.return_value = mock_message
        
        agent = LearningAgent()
        
        # Test generate_lesson_content
        topic = "Recursion"
        result = agent.generate_lesson_content(topic, "beginner")
        
        if result and 'cells' in result:
            print(f"[PASS] LearningAgent generated {len(result['cells'])} cells for topic '{topic}'")
            print(f"       First cell content: {result['cells'][0]['content']}")
        else:
            print(f"[FAIL] LearningAgent returned unexpected structure: {result}")

if __name__ == "__main__":
    verify_data()
    verify_handlers()
    verify_agent()
