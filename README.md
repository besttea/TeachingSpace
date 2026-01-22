# Python Learning Platform

A comprehensive web-based platform for learning Python programming with interactive Jupyter-style notebooks, coding exercises, and automated assessments.

## Features

### 🎓 Learning Class
- **Jupyter-Style Notebook Interface**: Create interactive lessons with multiple cell types
  - Text/Markdown cells with LaTeX math support
  - Code cells with syntax highlighting and execution
  - Image cells for visual content
  - Video cells (YouTube, Vimeo, or direct uploads)
- **Cell Management**: Drag-and-drop reordering, inline editing, version history
- **Progress Tracking**: Track student completion and time spent
- **Course Structure**: Organize content into courses → chapters → lessons

### 💪 Training Class
- **Coding Exercises**: Hands-on programming challenges with auto-grading
- **Progressive Hints**: Multi-level hint system with point penalties
- **Auto-Grading**: Automated test execution and scoring
- **Submission History**: Track all attempts and view detailed results
- **Points System**: Earn points for successful solutions
- **Difficulty Levels**: Beginner, Intermediate, and Advanced exercises

### 📝 Examination Class
- **Timed Assessments**: Create exams with time limits
- **Multiple Question Types**: Multiple choice, coding, and short answer
- **Auto-Grading**: Automated evaluation with AI assistance
- **Results Analytics**: Detailed performance analysis
- **Certificate Generation**: PDF certificates for completed exams

### 💬 AI Learning Assistant (Chat)
- **Interactive Chat**: Ask questions and get instant AI-powered answers
- **Resource Recommendations**: AI suggests relevant learning materials
- **Conversation History**: Save and manage multiple chat sessions
- **AJAX-Based Interface**: Smooth conversation experience without page reloads
- **Context-Aware**: Understands your learning needs and progress

### 🔐 Authentication System
- User registration and login
- Role-based access (Student, Instructor, Admin)
- Student profiles with progress tracking
- Dashboard with statistics and analytics

### 🛠️ Code Execution Engine
- **RestrictedPython**: Safe code execution for learning lessons
- **Dual Test Mode Support**:
  - stdin/stdout testing for input/output programs
  - Function-based testing for algorithm challenges
- **Sandboxing**: Restricted imports and operations for security
- **Resource Limits**: Timeout and memory controls
- Docker-based execution (planned) for advanced features

### 🤖 AI-Powered Features
- **Content Generation**: AI agents for creating lessons, exercises, and exams
- **Learning Agent**: Generates lesson content and code examples
- **Training Agent**: Creates coding exercises with test cases and hints
- **Examination Agent**: Generates exam questions and evaluates answers
- **Custom API Support**: Configure custom API endpoints for LLM services

## Technology Stack

### Backend
- **Django 5.0**: Full-stack web framework
- **Python 3.11+**: Programming language
- **SQLite/PostgreSQL**: Database
- **RestrictedPython**: Secure code execution

### Frontend
- **Bootstrap 5**: Responsive UI framework
- **Alpine.js**: Lightweight JavaScript framework
- **HTMX**: Dynamic HTML updates
- **CodeMirror 6**: Code editor
- **Marked.js**: Markdown rendering
- **KaTeX**: LaTeX math rendering
- **Prism.js**: Syntax highlighting
- **SortableJS**: Drag-and-drop functionality

## Project Structure

```
TeachingSpace/
├── apps/
│   ├── accounts/          # User authentication and profiles
│   ├── learning/          # Learning Class (notebooks, courses)
│   ├── training/          # Training Class (exercises, submissions)
│   ├── examination/       # Examination Class (exams, certificates)
│   ├── code_runner/       # Code execution engine
│   ├── ai_agents/         # AI content generation
│   └── video_generator/   # Manim video generation
├── config/
│   ├── settings/          # Django settings (base, dev, prod)
│   ├── urls.py            # URL configuration
│   └── wsgi.py / asgi.py  # WSGI/ASGI configuration
├── templates/             # HTML templates
│   ├── accounts/          # Auth templates
│   ├── learning/          # Learning templates
│   └── training/          # Training templates
├── static/                # Static files (CSS, JS, images)
├── media/                 # User-uploaded files
├── manage.py              # Django management script
└── requirements.txt       # Python dependencies
```

## Installation

### Prerequisites
- Python 3.11 or higher
- pip
- virtualenv (recommended)
- Git

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/besttea/TeachingSpace.git
   cd TeachingSpace
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv

   # On Windows
   venv\Scripts\activate

   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   # Copy example environment file
   cp .env.example .env

   # Edit .env and set your configuration
   # Required: SECRET_KEY, DEBUG, DATABASE settings
   ```

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run development server**
   ```bash
   python manage.py runserver
   ```

8. **Access the platform**
   - Open browser to: http://localhost:8000
   - Admin panel: http://localhost:8000/admin

## Database Models

### Learning App
- **Course**: Main course container with difficulty levels
- **Chapter**: Course sections
- **Lesson**: Notebook-style lessons
- **Cell**: Individual content cells (text, code, image, video)
- **CellVersion**: Cell edit history
- **Enrollment**: Student course enrollment
- **LessonProgress**: Track lesson completion

### Training App
- **Exercise**: Coding challenges
- **Hint**: Progressive hints
- **Submission**: Student code submissions
- **HintUsage**: Track hint views

### Accounts App
- **User**: Custom user model (Student, Instructor, Admin)
- **StudentProfile**: Extended profile with points and stats

## Usage Guide

### For Students

1. **Register** an account and login
2. **Browse Courses** and enroll in courses
3. **Study Lessons**:
   - Read text content
   - Run code examples
   - Watch video tutorials
4. **Practice Exercises**:
   - Solve coding challenges
   - View hints if stuck
   - Submit solutions for auto-grading
5. **Track Progress** on your dashboard

### For Instructors

1. **Create Courses** via Django admin
2. **Add Chapters and Lessons**
3. **Edit Lessons** using the notebook editor:
   - Add text, code, image, and video cells
   - Reorder cells by dragging
   - Preview in student view
4. **Create Exercises** with test cases and hints

### For Admins

- Full access to Django admin panel
- Manage users, courses, exercises
- View system statistics
- Monitor submissions and progress

## API Endpoints

### Learning API
- `POST /learning/api/cells/create/` - Create new cell
- `POST /learning/api/cells/<id>/update/` - Update cell
- `POST /learning/api/cells/<id>/delete/` - Delete cell
- `POST /learning/api/cells/<id>/execute/` - Execute code cell
- `POST /learning/api/cells/reorder/` - Reorder cells

### Training API
- `POST /training/exercises/<slug>/submit/` - Submit solution
- `POST /training/api/hints/<id>/view/` - View hint

### Chat API
- `POST /chat/api/send/` - Send message and get AI response
- `GET /chat/api/conversation/<id>/` - Get conversation messages
- `POST /chat/api/conversation/new/` - Create new conversation
- `DELETE /chat/api/conversation/<id>/delete/` - Delete conversation

## Development

### Running Tests
```bash
python manage.py test
```

### Code Style
Follow PEP 8 guidelines. Use:
```bash
flake8 .
black .
```

### Database Migrations
```bash
# Create new migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migrations
python manage.py showmigrations
```

## Recent Updates

### Version 1.1.0 (Latest)
- ✅ **Examination Class**: Full implementation with auto-grading and AI evaluation
- ✅ **AI Chat Assistant**: Interactive learning assistant with conversation history
- ✅ **Enhanced Code Executor**: Dual-mode testing (stdin/stdout and function-based)
- ✅ **AI Agents**: Learning, Training, and Examination agents for content generation
- ✅ **Custom API Support**: Configure custom LLM API endpoints
- ✅ **Notebook Import**: Import Jupyter notebooks with automatic chapter/lesson detection
- ✅ **Cell Handlers**: Modular architecture for different cell types
- 🔧 **Bug Fixes**: Template syntax errors, type errors in views

## Planned Features

- 🐳 **Docker Execution**: Full isolation for code execution
- 🎬 **Manim Integration**: AI-generated educational videos
- ⚡ **Celery Tasks**: Async processing for heavy operations
- 📊 **Analytics Dashboard**: Advanced progress tracking
- 💬 **Discussion Forums**: Student collaboration
- 🏆 **Gamification**: Badges, leaderboards, achievements
- 📱 **Mobile App**: Native iOS and Android applications

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with Django framework
- UI components from Bootstrap
- Code editor powered by CodeMirror
- Markdown rendering by Marked.js
- Math rendering by KaTeX
- Developed with assistance from Claude AI

## Contact

- GitHub: [@besttea](https://github.com/besttea)
- Email: best-tea@163.com

## Project Status

**Current Version**: 1.1.0

### Completed ✅
- ✅ **Authentication System**: User registration, login, role-based access
- ✅ **Learning Class**: Jupyter-style notebook interface with cell management
- ✅ **Training Class**: Coding exercises with auto-grading and hints
- ✅ **Examination Class**: Timed assessments with multiple question types
- ✅ **Code Execution Engine**: RestrictedPython with dual-mode testing
- ✅ **AI Chat Assistant**: Interactive Q&A with conversation history
- ✅ **AI Agents**: Content generation for lessons, exercises, and exams
- ✅ **Notebook Import**: Import from Jupyter .ipynb files
- ✅ **Progress Tracking**: Course progress and completion tracking
- ✅ **Responsive UI**: Bootstrap 5 with modern design

### In Progress 🚧
- 🚧 **Video Generation**: Manim integration for educational videos
- 🚧 **Docker Execution**: Full isolation for code execution
- 🚧 **Celery Integration**: Async task processing
- 🚧 **Advanced Analytics**: Detailed learning analytics dashboard

### Planned 📋
- 📋 **Discussion Forums**: Student collaboration and Q&A
- 📋 **Gamification**: Badges, achievements, and leaderboards
- 📋 **Mobile App**: Native iOS and Android applications
- 📋 **Social Features**: Student profiles and networking
- 📋 **Content Marketplace**: Share and sell courses

---

**Note**: This platform is under active development. Some features may be incomplete or subject to change.
