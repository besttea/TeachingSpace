from .base_agent import BaseAgent
import json

class ExaminationAgent(BaseAgent):
    """
    AI Agent for generating exam questions and evaluating student answers.
    """
    
    def process_request(self, request_data):
        """
        Process a request to generate an exam.
        Expected request_data: {'topic': str, 'difficulty': str, 'question_count': int}
        """
        topic = request_data.get('topic')
        difficulty = request_data.get('difficulty', 'intermediate')
        question_count = request_data.get('question_count', 5)
        
        return self.generate_exam_questions(topic, difficulty, question_count)

    def generate_exam_questions(self, topic, difficulty, count=5):
        """
        Generate a set of exam questions (MCQ, True/False, Code, Essay).
        """
        system_prompt = f"""
        You are an expert examiner creating a Python certification exam.
        Create {count} diverse questions on '{topic}' for {difficulty} level.
        
        Output Structure:
        Return a JSON object with a 'questions' key, containing a list of question objects.
        
        Question Types & Formats:
        
        1. Multiple Choice (type='multiple_choice'):
           {{
               "type": "multiple_choice",
               "text": "Question text...",
               "points": 5,
               "options": {{"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"}},
               "correct_answer": "A",
               "explanation": "Why A is correct..."
           }}
           
        2. True/False (type='true_false'):
           {{
               "type": "true_false",
               "text": "Statement...",
               "points": 2,
               "correct_answer": true,
               "explanation": "Why it is true..."
           }}
           
        3. Code (type='code'):
           {{
               "type": "code",
               "text": "Write a function that...",
               "points": 10,
               "starter_code": "def func():\\n    pass",
               "solution_code": "def func():\\n    return True",
               "test_cases": [{{"input": "...", "expected_output": "...", "is_hidden": false}}]
           }}
           
        4. Essay/Short Answer (type='essay'):
           {{
               "type": "essay",
               "text": "Explain the concept of...",
               "points": 5,
               "word_limit": 200,
               "rubric": "Key points to mention...",
               "sample_answer": "A good answer would be..."
           }}
        """
        
        prompt = f"""
        Create a {difficulty} level exam on {topic} with {count} questions.
        Include a mix of Multiple Choice, True/False, and at least one Coding question.
        Ensure questions test understanding, not just memorization.
        """

        result = self.generate_json(prompt, system_prompt)
        if isinstance(result, list):  # model dropped the {"questions": ...} wrapper
            return {'questions': result}
        return result

    def modify_question(self, question, instruction):
        """
        Modify an existing exam question per a natural-language instruction.

        Args:
            question: dict with the current question (type, text, points,
                explanation, plus type-specific fields: options/correct_answer,
                starter_code/solution_code/test_cases, word_limit/rubric/
                sample_answer, or correct_answer for true_false).
            instruction: what to change, e.g. "把题干改得更口语化，选项 B 的
                表述再清楚一些".

        Returns the UPDATED question dict (same structure). The caller
        re-validates code questions before applying.
        """
        import json

        current = json.dumps(question, ensure_ascii=False, indent=2)
        prompt = f"""
        Current exam question:
        {current}

        Instructor instruction:
        {instruction}

        Return the UPDATED question as JSON with the SAME structure and the
        SAME type. Rules:
        1. Keep unchanged parts exactly as they are.
        2. Apply the instruction precisely — do not redesign the question.
        3. For code questions: if test cases change, the solution_code must
           still pass ALL of them.
        4. Keep the answer correct and unambiguous.
        """

        system_prompt = (
            'You are an expert examiner maintaining an exam question bank. '
            'Return JSON only.')
        result = self.generate_json(prompt, system_prompt)
        if isinstance(result, list):
            result = result[0] if result else {}
        return result

    def evaluate_essay_answer(self, question_text, student_answer, rubric, sample_answer):
        """
        Evaluate a student's essay answer against a rubric.
        """
        system_prompt = "You are a strict but fair exam grader."
        
        prompt = f"""
        Question: {question_text}
        
        Rubric: {rubric}
        Sample Answer: {sample_answer}
        
        Student Answer:
        {student_answer}
        
        Evaluate the student's answer.
        Return JSON:
        {{
            "score_percentage": 85,  (0-100)
            "feedback": "Detailed feedback...",
            "key_points_covered": ["point 1", "point 2"],
            "missed_points": ["point 3"]
        }}
        """
        
        return self.generate_json(prompt, system_prompt)
