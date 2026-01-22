# AI Agents System

This module contains AI-powered agents for automated content generation in the Python Learning Platform.

## Overview

The AI Agents system uses Anthropic's Claude API to generate educational content and provide interactive assistance. The system includes:

1. **Learning Agent** - Generates lesson content, explanations, and code examples
2. **Training Agent** - Creates coding exercises, test cases, and hints
3. **Examination Agent** - Generates exam questions and evaluates student submissions
4. **Chat AI Service** - Interactive learning assistant with conversation history management

## Architecture

### Base Agent (`base_agent.py`)
The `BaseAgent` class provides common functionality:
- Anthropic API client management
- Error handling and retry logic
- Token usage tracking
- Response validation
- Rate limiting
- Cost monitoring

### Specialized Agents

#### Learning Agent (`learning_agent.py`)
Generates content for the Learning Class:
- Full lesson content with markdown formatting
- Code examples with explanations
- Interactive exercises
- Video tutorial scripts (optional)

#### Training Agent (`training_agent.py`)
Creates practice exercises:
- Coding challenge descriptions
- Test cases (input/output pairs)
- Progressive hints
- Solution code with explanations
- Difficulty assessment

#### Examination Agent (`examination_agent.py`)
Handles assessment content:
- Multiple choice questions
- Coding problems
- Short answer questions
- Automated grading for objective questions
- Feedback generation for student submissions

#### Chat AI Service (`apps/chat/ai_service.py`)
Provides interactive learning assistance:
- Real-time Q&A with students
- Context-aware responses based on student progress
- Resource recommendations from ClassLib
- Conversation history management
- Multi-turn conversations with memory

## Usage

### Basic Usage

```python
from apps.ai_agents.learning_agent import LearningAgent

# Initialize agent
agent = LearningAgent()

# Generate a lesson
lesson_content = agent.generate_lesson(
    topic="Python Variables",
    difficulty="beginner",
    learning_objectives=["Understand variable declaration", "Know data types"],
    duration_minutes=15
)
```

### Async Usage with Celery

```python
from apps.ai_agents.tasks import generate_lesson_async

# Queue lesson generation
task = generate_lesson_async.delay(
    topic="Python Functions",
    difficulty="intermediate"
)

# Check status
if task.ready():
    result = task.result
```

## Prompt Engineering

Prompts are stored in the `prompts/` directory as reusable templates:

- `prompts/lesson_template.txt` - Lesson generation
- `prompts/exercise_template.txt` - Exercise creation
- `prompts/question_template.txt` - Exam question generation
- `prompts/evaluation_template.txt` - Answer evaluation

### Prompt Variables

Templates support variable substitution:
- `{topic}` - The subject matter
- `{difficulty}` - beginner, intermediate, advanced
- `{context}` - Additional context or requirements
- `{examples}` - Few-shot examples

## Configuration

Set environment variables in `.env`:

```bash
# Required
ANTHROPIC_API_KEY=your-api-key

# Optional (with defaults)
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_BASE_URL=  # Optional: Custom API endpoint (e.g., for proxies)
AI_MAX_TOKENS=4096
AI_TEMPERATURE=0.7
AI_CACHE_ENABLED=True
AI_COST_LIMIT_DAILY=50.00
```

### Custom API Endpoints

If you're using a custom API endpoint (e.g., a proxy or alternative provider), set:

```bash
ANTHROPIC_BASE_URL=https://your-custom-endpoint.com/anthropic
```

This is useful for:
- Using API proxies
- Implementing custom rate limiting
- Adding request logging
- Testing with mock endpoints

## Content Validation

All generated content goes through validation:

1. **Syntax Validation** - Code is checked for syntax errors
2. **Test Execution** - Test cases are run to verify correctness
3. **Quality Checks** - Content is scored on clarity, relevance, accuracy
4. **Manual Review** - Critical content (exams) requires instructor approval

## Cost Management

- Track token usage per generation
- Set daily cost limits
- Cache frequently requested content
- Monitor API usage in admin dashboard

## Error Handling

Agents implement robust error handling:
- Automatic retry with exponential backoff
- Fallback to cached content when available
- Detailed logging for debugging
- Graceful degradation

## Testing

```bash
# Test AI agent connectivity
python manage.py test_ai_agents --settings=config.settings.development

# Run agent unit tests (with mocking)
pytest apps/ai_agents/tests/

# Test specific agent
pytest apps/ai_agents/tests/test_learning_agent.py
```

## Best Practices

1. **Always validate generated content** before presenting to students
2. **Use appropriate temperature** - Lower (0.3-0.5) for factual content, higher (0.7-0.9) for creative
3. **Implement caching** to reduce costs and improve response times
4. **Monitor quality** - Track user feedback and adjust prompts accordingly
5. **Human oversight** - Especially for exam content and grading
6. **Rate limiting** - Prevent abuse and manage costs
7. **Logging** - Store all prompts and responses for debugging and improvement

## Future Enhancements

- Multi-LLM support (fallback to OpenAI GPT-4)
- Fine-tuned models for specific content types
- Student interaction analysis for personalized content
- Automated prompt optimization based on outcomes
- Real-time streaming for better UX
- Multi-language support
