# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Python Learning Platform** - A Django-based web application for teaching and learning Python programming with three main sections:

1. **Learning Class**: Jupyter-style notebook interface with cell-based content (text, code, images, videos). Students and instructors can create, edit, and arrange content cells interactively. AI agent generates lessons, exercises, and educational videos using Manim (mathematical animation library).

2. **Training Class**: Coding exercises with auto-grading, hints, difficulty levels, and submission history. AI agent generates exercises and progressive hints. Uses notebook-style interface for exercise description and code submission.

3. **Examination Class**: Timed assessments with multiple question types, results analytics, and certificate generation. AI agent generates exam questions and evaluates student submissions with detailed feedback.

### Notebook-Style Interface

The platform adopts a **Jupyter-like cell-based interface** for maximum flexibility and interactivity:

- **Text Cells**: Markdown-based text with rich formatting, LaTeX math support
- **Code Cells**: Interactive Python code editor with execution and output display
- **Image Cells**: Upload or embed images with captions and annotations
- **Video Cells**: Embedded videos (YouTube, Vimeo) or AI-generated Manim animations
- **Cell Operations**: Add, delete, reorder, duplicate, and merge cells
- **Collaborative Editing**: Real-time updates for instructor-student interaction
- **Version Control**: Track changes and restore previous versions

## Technology Stack

- **Backend**: Django 5.0 (Python web framework)
- **Database**: SQLite (development), PostgreSQL (production) with JSONField for cell storage
- **Frontend**: Django Templates + Bootstrap 5 + Alpine.js + HTMX
- **Notebook Interface**:
  - **SortableJS**: Drag-and-drop cell reordering
  - **CodeMirror 6**: Code cell editor with Python syntax highlighting
  - **Marked.js**: Markdown rendering for text cells
  - **KaTeX/MathJax**: LaTeX math equation rendering
  - **Prism.js**: Syntax highlighting for output
- **Code Execution**: Docker containers (for security) + RestrictedPython (for simple cases)
- **Video Generation**:
  - **Manim Community Edition**: Generate mathematical animations and educational videos
  - **FFmpeg**: Video encoding and processing
- **Task Queue**: Celery + Redis (for async operations, video generation)
- **PDF Generation**: WeasyPrint (for certificates)
- **File Storage**:
  - Local filesystem (development)
  - S3-compatible storage (production) for images and videos
- **AI/LLM Integration**: Anthropic Claude API (for content generation and evaluation)
  - **Learning Agent**: Generates lessons, explanations, code examples, and Manim video scripts
  - **Training Agent**: Creates coding exercises, test cases, and hints
  - **Examination Agent**: Generates exam questions and evaluates student answers
  - **Video Agent**: Generates Manim animation scripts from lesson content

## Project Structure

```
teaching_space/
├── config/                    # Django project configuration
│   ├── settings/
│   │   ├── base.py           # Common settings
│   │   ├── development.py    # Development settings
│   │   └── production.py     # Production settings
│   ├── urls.py               # Root URL configuration
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── accounts/             # User authentication & profiles
│   ├── learning/             # Learning Class (courses, lessons)
│   │   ├── models.py         # Course, Lesson, Cell models
│   │   ├── views.py          # Notebook interface views
│   │   ├── serializers.py    # Cell CRUD API serializers
│   │   └── cell_handlers/    # Cell type handlers
│   │       ├── text_cell.py
│   │       ├── code_cell.py
│   │       ├── image_cell.py
│   │       └── video_cell.py
│   ├── training/             # Training Class (exercises, submissions)
│   ├── examination/          # Examination Class (exams, certificates)
│   ├── code_runner/          # Code execution engine
│   ├── video_generator/      # Manim video generation
│   │   ├── manim_engine.py   # Manim script executor
│   │   ├── script_validator.py # Validate Manim scripts
│   │   ├── templates/        # Manim scene templates
│   │   └── output/           # Generated video files
│   ├── ai_agents/            # AI agent system for content generation
│   │   ├── learning_agent.py    # Lesson & exercise generator
│   │   ├── training_agent.py    # Exercise & hint generator
│   │   ├── examination_agent.py # Question & evaluation agent
│   │   ├── video_agent.py       # Manim script generator
│   │   ├── base_agent.py        # Base AI agent class
│   │   └── prompts/             # Prompt templates
│   └── core/                 # Shared utilities
├── templates/                # Django HTML templates
│   ├── notebook/             # Notebook interface templates
│   │   ├── notebook_editor.html
│   │   ├── cell_text.html
│   │   ├── cell_code.html
│   │   ├── cell_image.html
│   │   └── cell_video.html
├── static/                   # Static files (CSS, JS, images)
│   ├── js/
│   │   ├── notebook.js       # Notebook interface logic
│   │   ├── cell_manager.js   # Cell operations (add, delete, reorder)
│   │   ├── code-editor.js    # CodeMirror integration
│   │   └── markdown-renderer.js # Markdown + LaTeX rendering
├── media/                    # User-uploaded files
│   ├── images/               # Cell images
│   ├── videos/               # Generated and uploaded videos
│   └── notebooks/            # Exported notebooks
└── docker/                   # Docker configuration files
```

## Common Development Commands

### Environment Setup

```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Activate virtual environment (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Database Commands

```bash
# Create migrations
python manage.py makemigrations --settings=config.settings.development

# Apply migrations
python manage.py migrate --settings=config.settings.development

# Create superuser
python manage.py createsuperuser --settings=config.settings.development
```

### Running the Development Server

```bash
# Run development server
python manage.py runserver --settings=config.settings.development

# Run on specific port
python manage.py runserver 8080 --settings=config.settings.development
```

### Testing Commands

```bash
# Run all tests
pytest

# Run specific app tests
pytest apps/accounts/tests/

# Run with coverage
pytest --cov=apps
```

### AI Agent Commands

```bash
# Generate lesson content for a topic
python manage.py generate_lesson "Variables and Data Types" --difficulty beginner --settings=config.settings.development

# Generate coding exercises
python manage.py generate_exercises --topic "Functions" --count 5 --difficulty intermediate --settings=config.settings.development

# Generate exam questions
python manage.py generate_exam --course "python-basics" --question-count 20 --settings=config.settings.development

# Generate Manim video script for a topic
python manage.py generate_video_script "List Comprehensions" --difficulty intermediate --settings=config.settings.development

# Execute Manim script and generate video
python manage.py render_manim_video --script-id 123 --quality medium --settings=config.settings.development

# Batch generate content (async with Celery)
python manage.py batch_generate_content --course-id 1 --settings=config.settings.development

# Test AI agent connectivity
python manage.py test_ai_agents --settings=config.settings.development
```

### Notebook & Video Commands

```bash
# Export notebook to various formats
python manage.py export_notebook --lesson-id 1 --format json --settings=config.settings.development
python manage.py export_notebook --lesson-id 1 --format pdf --settings=config.settings.development

# Import notebook from JSON
python manage.py import_notebook --file notebook.json --course-id 1 --settings=config.settings.development

# Generate video from existing lessons
python manage.py batch_generate_videos --course-id 1 --settings=config.settings.development

# Clean up old video renders
python manage.py cleanup_videos --older-than 30 --settings=config.settings.development

# Optimize images in cells
python manage.py optimize_cell_images --settings=config.settings.development
```

## Key Architecture Decisions

### Custom User Model
- **Location**: `apps/accounts/models.py`
- **Model**: `User` (extends AbstractUser)
- **Important**: The custom User model is referenced as `AUTH_USER_MODEL = "accounts.User"` in settings
- All user-related operations should use this custom model

### Django Apps Structure
- Each app in the `apps/` directory has its `name` configured as `apps.<app_name>` in `apps.py`
- Example: `AccountsConfig.name = "apps.accounts"`
- This ensures proper module resolution

### Settings Organization
- **Base settings**: `config/settings/base.py` - Common configuration
- **Development settings**: `config/settings/development.py` - SQLite, debug mode
- **Production settings**: `config/settings/production.py` - PostgreSQL, security hardening
- Use `--settings=config.settings.development` flag when running manage.py commands

### Notebook-Style Interface Architecture
- **Cell-Based Model**: Each lesson is composed of multiple cells stored as JSON
  - `Cell` model with polymorphic type field (text, code, image, video)
  - JSONField stores cell-specific data (markdown content, code, image URL, video URL)
  - Order field for sequence management
  - Version tracking for edit history
- **Frontend Implementation**:
  - SortableJS for drag-and-drop cell reordering
  - Alpine.js for reactive cell state management
  - HTMX for dynamic cell CRUD without page reload
  - CodeMirror 6 for code cells with Python syntax
  - Marked.js + KaTeX for text cells with math support
- **Real-time Collaboration** (Future):
  - WebSocket connection for live updates
  - Operational Transform (OT) for conflict resolution
  - User presence indicators
- **Export/Import**:
  - JSON format compatible with Jupyter notebooks (.ipynb)
  - Export to PDF, HTML, or standalone Python script
  - Import from .ipynb files with cell conversion

### Video Generation Architecture
- **Manim Integration**:
  - Manim Community Edition for mathematical animations
  - Python-based scene generation from scripts
  - Render queue managed by Celery for async processing
  - Multiple quality levels (low/medium/high) for different use cases
- **AI-Generated Video Scripts**:
  - Video Agent generates Manim Python code from lesson content
  - Script validation before execution (syntax check, security)
  - Template-based generation for common animation patterns
  - Scene composition: intro → content → examples → summary
- **Video Storage**:
  - Local filesystem for development
  - S3/CloudFront for production (CDN delivery)
  - Video metadata stored in database (duration, resolution, file size)
  - Thumbnail generation for preview
- **Rendering Pipeline**:
  1. AI generates Manim script → 2. Validate script → 3. Queue Celery task →
  4. Execute Manim in isolated environment → 5. Encode with FFmpeg →
  6. Upload to storage → 7. Update database → 8. Notify user
- **Video Cell Display**:
  - HTML5 video player with custom controls
  - Lazy loading for performance
  - Fallback to YouTube/Vimeo embed if URL provided
  - Interactive annotations (future: clickable timestamps)

### Code Execution Security
- **Docker isolation**: User code runs in isolated containers with resource limits
- **RestrictedPython**: For simple code examples in Learning Class
- **Security measures**: Network disabled, memory limits, CPU quotas, timeout enforcement

### AI Agent Architecture
- **Base Agent Class**: `apps/ai_agents/base_agent.py` - Common functionality for all AI agents
  - API client management (Anthropic Claude)
  - Error handling and retry logic
  - Token usage tracking
  - Response validation
- **Specialized Agents**:
  - **Learning Agent** (`learning_agent.py`): Generates lesson content, explanations, code examples
  - **Training Agent** (`training_agent.py`): Creates exercises, test cases, hints, and solutions
  - **Examination Agent** (`examination_agent.py`): Generates questions, evaluates answers, provides feedback
  - **Video Agent** (`video_agent.py`): Generates Manim animation scripts from lesson topics and content
- **Prompt Engineering**: Structured prompts in `apps/ai_agents/prompts/` directory
  - Templates for different content types
  - Context-aware generation based on difficulty level
  - Few-shot examples for consistency
- **Content Validation**: Generated content is validated before saving to database
  - Code syntax verification
  - Test case execution
  - Content quality checks
- **Async Processing**: AI generation tasks run asynchronously via Celery to avoid blocking
- **Caching Strategy**: Cache frequently requested generations to reduce API calls and costs
- **Documentation**: See `apps/ai_agents/README.md` for detailed usage and examples

## AI Agent Workflow

### Content Generation Flow

1. **Request Initiation**
   - Instructor or system triggers content generation
   - Request saved to `AIGenerationRequest` model with status "pending"
   - Task queued in Celery with priority

2. **Agent Processing**
   - Appropriate agent selected (Learning/Training/Examination)
   - Prompt template loaded with context variables
   - API request sent to Anthropic Claude
   - Response streamed or received in full

3. **Content Validation**
   - Syntax validation for code blocks
   - Test case execution for exercises
   - Quality scoring algorithm applied
   - Results saved to `ContentValidation` model

4. **Storage & Review**
   - Valid content saved to respective model (Lesson/Exercise/Question)
   - Generation history logged with token usage and cost
   - If validation fails, retry with adjusted prompt or flag for manual review
   - Critical content (exams) queued for instructor approval

5. **Monitoring & Analytics**
   - Track success rate per agent and content type
   - Monitor API costs and token usage
   - Analyze generation time and quality scores
   - Update prompt templates based on performance

### Example Workflows

**Instructor Generates a Lesson:**
```
Instructor → Form Submit → Celery Task → Learning Agent →
Claude API → Validation → Save Lesson → Notify Instructor
```

**Batch Generate Course Content:**
```
Admin → Batch Command → Multiple Celery Tasks → Agents Process →
Validation Pipeline → Database Storage → Report Generated
```

**Student Exam Evaluation:**
```
Student Submits → Examination Agent → Claude API →
Evaluate Answer → Calculate Score → Generate Feedback → Save Result
```

## Database Models

### Accounts App
- `User`: Custom user model with user_type (student/instructor/admin)
- `StudentProfile`: Extended profile with points, experience level, streak tracking

### Learning App (✅ Implemented)
- `Course`: Course container with difficulty levels
- `Chapter`: Sections within courses
- `Lesson`: Notebook-style lesson container
  - Title, description, course/chapter relationship
  - Status (draft, published, archived)
  - Version tracking
  - Export format preferences
- `Cell`: Individual content cells within lessons (Jupyter-style)
  - **Polymorphic types**: text, code, image, video
  - **Common fields**: lesson_id, order, created_at, updated_at
  - **Type-specific data** (stored in JSONField):
    - **Text Cell**: markdown content, rendered HTML cache
    - **Code Cell**: Python code, output, execution status, execution_time
    - **Image Cell**: image_url, caption, alt_text, dimensions
    - **Video Cell**: video_url, video_type (uploaded/manim/youtube/vimeo), duration, thumbnail_url
  - Version history for undo/redo
  - Metadata (author, last_editor, edit_count)
- `CellVersion`: Track cell edit history
  - Cell snapshot (JSON)
  - Editor user
  - Change description
  - Timestamp
- `Video`: Video tutorials and Manim animations
  - Source type (manim_generated, uploaded, external)
  - Manim script (if AI-generated)
  - File path or external URL
  - Metadata (duration, resolution, file_size)
  - Thumbnail image
  - Generation status (pending, rendering, completed, failed)
  - Associated lesson/cell
- `Enrollment`: Student course enrollment
- `LessonProgress`: Track lesson completion and cell interaction
  - Time spent per cell
  - Code cells executed
  - Progress percentage

### Training App (✅ Implemented)
- `Exercise`: Coding challenges
- `Hint`: Progressive hints
- `Submission`: Student code submissions
- `HintUsage`: Track hint views

### Examination App (✅ Implemented)
- `Exam`: Timed assessments
- `Question`: Base question model (polymorphic)
- `MultipleChoiceQuestion`, `CodingQuestion`, `ShortAnswerQuestion`
- `ExamAttempt`: Student exam sessions
- `Answer`: Student answers
- `Certificate`: Generated PDFs

### Chat App (✅ Implemented)

- `ChatConversation`: Chat conversation sessions
  - User reference
  - Title (auto-generated from first message)
  - Created and updated timestamps
  - Active status
- `ChatMessage`: Individual messages in conversations
  - Role (user, assistant, system)
  - Content text
  - Metadata (suggested resources)
  - Created timestamp
- `LearningResource`: Available learning resources
  - Title, filename, file path
  - Description and topics
  - Difficulty level

### AI Agents App (✅ Partially Implemented)
- `AIGenerationRequest`: Track content generation requests
  - Request type (lesson, exercise, question, **video_script**)
  - Input parameters (topic, difficulty, etc.)
  - Status (pending, processing, completed, failed)
  - Associated course/chapter/lesson
- `AIGenerationHistory`: Audit log of all AI generations
  - Prompt used
  - Response received
  - Token usage
  - Generation time
  - Cost tracking
- `PromptTemplate`: Store and version prompt templates
  - Template name and category
  - Template content with variables
  - Version history
  - Performance metrics
- `ContentValidation`: Validation results for AI-generated content
  - Syntax checks
  - Test execution results
  - Quality scores
  - Manual review status
- **Video Generation Models**:
  - `ManimScript`: AI-generated Manim animation scripts
    - Script content (Python code)
    - Associated lesson/topic
    - Validation status
    - Generation parameters
  - `VideoRenderJob`: Track video rendering tasks
    - Manim script reference
    - Render status (queued, rendering, completed, failed)
    - Quality level (low/medium/high)
    - Render time
    - Output file path
    - Error logs
    - Celery task ID

## Environment Variables

Create a `.env` file based on `.env.example`:
- `SECRET_KEY`: Django secret key
- `DEBUG`: Debug mode (True/False)
- `DB_*`: Database configuration
- `REDIS_URL`: Redis connection for Celery
- `EMAIL_*`: Email configuration
- **AI/LLM Configuration**:
  - `ANTHROPIC_API_KEY`: Anthropic Claude API key (required for AI agents)
  - `ANTHROPIC_MODEL`: Model version (default: claude-3-5-sonnet-20241022)
  - `AI_MAX_TOKENS`: Maximum tokens per request (default: 4096)
  - `AI_TEMPERATURE`: Generation temperature 0-1 (default: 0.7)
  - `AI_CACHE_ENABLED`: Enable response caching (True/False)
  - `AI_COST_LIMIT_DAILY`: Daily cost limit in USD (optional)
- **Video Generation Configuration**:
  - `MANIM_QUALITY`: Default render quality (low/medium/high/production)
  - `MANIM_OUTPUT_DIR`: Directory for rendered videos
  - `FFMPEG_PATH`: Path to FFmpeg executable
  - `VIDEO_STORAGE_BACKEND`: Storage backend (local/s3)
  - `S3_BUCKET_NAME`: S3 bucket for video storage (if using S3)
  - `CDN_URL`: CloudFront or CDN URL for video delivery

## Current Implementation Status

**Completed:**
- ✅ Django project structure
- ✅ Settings organization (base/dev/prod)
- ✅ Custom User model and StudentProfile
- ✅ Database migrations applied
- ✅ Admin interface for User management
- ✅ Authentication views (register, login, dashboard)
- ✅ **Notebook-Style Interface**:
  - ✅ Cell model and database schema
  - ✅ Cell type handlers (text, code, image, video)
  - ✅ Frontend notebook editor with cell operations
  - ✅ Drag-and-drop cell reordering
  - ✅ Real-time cell execution
  - ✅ Markdown + LaTeX rendering
  - ✅ Notebook import from .ipynb files
- ✅ Learning app models and views
- ✅ Training app models and views
- ✅ Examination app models and views
- ✅ Code execution engine (RestrictedPython with dual-mode testing)
- ✅ **AI Chat Assistant**:
  - ✅ Chat interface with conversation history
  - ✅ AI-powered responses with resource recommendations
  - ✅ AJAX-based conversation management
  - ✅ Custom API endpoint support
- ✅ **AI Agent System**:
  - ✅ Base agent class with Anthropic API integration
  - ✅ Learning agent (lesson generation)
  - ✅ Training agent (exercise generation)
  - ✅ Examination agent (question generation & evaluation)
  - ✅ Custom API base URL support

**In Progress/Pending:**
- ⏳ Version control and undo/redo for cells
- ⏳ Export/import (PDF, standalone Python script)
- ⏳ Frontend templates refinement
- ⏳ **Video Generation System**:
  - ⏳ Manim integration and rendering pipeline
  - ⏳ AI video script generation (Video Agent)
  - ⏳ Async video rendering with Celery
  - ⏳ Video storage and CDN integration
  - ⏳ Thumbnail generation
  - ⏳ Video cell display and playback
- ⏳ Docker configuration for isolated code execution
- ⏳ **Advanced AI Features**:
  - ⏳ Prompt template management
  - ⏳ Content validation pipeline
  - ⏳ AI generation tracking and analytics
  - ⏳ Cost monitoring and rate limiting
  - ⏳ Batch content generation

## Next Steps

1. Implement authentication views and templates
2. **Create Notebook-Style Interface**:
   - Design and implement Cell model with polymorphic types
   - Build cell type handlers (text, code, image, video)
   - Create frontend notebook editor with Alpine.js/HTMX
   - Implement drag-and-drop with SortableJS
   - Add markdown rendering with KaTeX for math
   - Build cell CRUD API endpoints
   - Implement version control for cells
   - Add export/import functionality (.ipynb compatible)
3. Create models for Learning, Training, and Examination apps
4. **Build Video Generation System**:
   - Set up Manim Community Edition
   - Create video generation pipeline with Celery
   - Implement Manim script validator
   - Build video storage system (local/S3)
   - Add thumbnail generation with FFmpeg
   - Create video cell display component
5. **Build AI Agent System**:
   - Set up Anthropic API integration
   - Create base agent class with error handling
   - Implement learning agent for lesson generation
   - Implement training agent for exercise generation
   - Implement examination agent for question generation
   - **Implement video agent for Manim script generation**
   - Build prompt template system
   - Add content validation pipeline
   - Implement cost tracking and rate limiting
6. Build code execution engine with Docker
7. Create frontend templates with Bootstrap and CodeMirror
8. Implement views for all three main sections
9. **Integrate AI agents with notebook interface**:
   - Admin interface for content generation
   - Instructor tools for AI-assisted notebook creation
   - Real-time generation progress tracking
   - Bulk generation for courses
10. Add tests (including AI agent tests with mocking, Manim rendering tests)
11. Deploy to production with CDN for video delivery

## Notes for Future Development

- Always use the custom User model (`apps.accounts.models.User`)
- Run commands with appropriate settings module
- Code execution must be properly sandboxed (use Docker)
- Test security features thoroughly before production
- Keep models DRY - use abstract base classes where appropriate
- **Notebook Interface Best Practices**:
  - Store cell data as JSON for flexibility and versioning
  - Implement optimistic updates for better UX
  - Use WebSocket for real-time collaboration features
  - Cache rendered markdown and LaTeX for performance
  - Implement auto-save every 30 seconds
  - Validate cell order integrity on save
  - Support keyboard shortcuts (Shift+Enter to run code, etc.)
  - Implement cell output truncation for large results
  - Add cell execution timeout to prevent hanging
  - Store cell execution history for analytics
- **Video Generation Best Practices**:
  - Always validate Manim scripts before execution
  - Use sandboxed environment for Manim rendering
  - Implement render queue with priority levels
  - Generate multiple quality versions for adaptive streaming
  - Store raw Manim output for re-rendering if needed
  - Implement automatic retry on render failure
  - Monitor disk space for video output directory
  - Clean up failed renders automatically
  - Generate thumbnails at consistent timestamps
  - Implement video preview before full render (low quality)
  - Track render time and cost per video
  - Consider video compression to reduce storage costs
- **AI Agent Best Practices**:
  - Always validate AI-generated content before displaying to students
  - Monitor API costs and set appropriate rate limits
  - Cache frequently generated content to reduce API calls
  - Use appropriate temperature settings (lower for factual content, higher for creative)
  - Implement retry logic with exponential backoff for API failures
  - Store prompts and responses for debugging and improvement
  - Regularly review and update prompt templates based on output quality
  - Consider using streaming responses for better UX on long generations
  - Implement human review workflow for critical content (exams, grading)
  - Track token usage per user/course for cost allocation
  - **Video Agent Specifics**:
    - Validate generated Manim code syntax before queuing render
    - Include error handling in generated scripts
    - Test common animation patterns regularly
    - Maintain library of reusable scene components
    - Document Manim version compatibility
- **Content Quality**:
  - AI-generated code must pass syntax checks before saving
  - Test cases should be executed to verify correctness
  - Manual review required for exam questions before use
  - Implement feedback loop to improve prompt quality over time
  - **Video Quality**:
    - Review generated videos before publishing
    - Check audio sync if narration added
    - Verify animation accuracy for mathematical content
    - Test video playback across devices
- **Scalability Considerations**:
  - Use Celery for async AI generation and video rendering
  - Implement queue priorities (urgent vs batch generation)
  - Consider implementing a content approval workflow
  - Plan for multi-LLM support (fallback to OpenAI if needed)
  - Use CDN for video delivery to reduce bandwidth costs
  - Implement lazy loading for video cells
  - Consider video streaming protocols (HLS/DASH) for large files
  - Archive old videos to cold storage
  - Implement cell-level caching strategy
  - Use database indexing for cell queries
  - Consider sharding for large-scale deployments