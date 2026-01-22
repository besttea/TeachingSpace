# Changelog

All notable changes to the Python Learning Platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-01-23

### Added

#### Learning Class
- **Notebook Import Feature**: Import Jupyter notebooks (.ipynb) with automatic chapter and lesson detection
- **Cell Handlers**: Modular architecture for different cell types (text, code, image, video)
- **Enhanced Content Management**: Management commands for loading course content
- **Version Control**: Track cell edit history with restore capability

#### Training Class
- **Dual-Mode Testing**: Support for both stdin/stdout and function-based testing
- **Enhanced Code Executor**: Improved test execution with better error handling
- **Training Agent**: AI-powered exercise generation with test cases and hints

#### Examination Class
- **Complete Implementation**: Full examination system with timed assessments
- **Multiple Question Types**: Support for multiple choice, coding, and short answer questions
- **Examination Agent**: AI-powered question generation and evaluation
- **Results Analytics**: Detailed performance analysis and scoring
- **Status Tracking**: Track exam status (draft, published, archived)

#### AI Chat Assistant
- **Interactive Chat Interface**: Real-time Q&A with AI learning assistant
- **Conversation History**: Save and manage multiple chat sessions
- **AJAX-Based UI**: Smooth conversation experience without page reloads
- **Resource Recommendations**: AI suggests relevant learning materials from ClassLib
- **Context-Aware Responses**: AI understands student learning needs and progress

#### AI-Powered Features
- **Base Agent Class**: Shared functionality for all AI agents
- **Learning Agent**: Generates lesson content and code examples
- **Training Agent**: Creates coding exercises with test cases
- **Examination Agent**: Generates exam questions and evaluates answers
- **Custom API Support**: Configure custom LLM API endpoints (ANTHROPIC_BASE_URL)

### Changed

- **Code Executor**: Refactored to support both stdin/stdout and function-based testing modes
- **Test Case Format**: Flexible test case format supporting both input/output and function evaluation
- **AI Service**: Enhanced with support for custom API base URLs
- **Settings Configuration**: Added comprehensive AI/LLM configuration options

### Fixed

- **Template Syntax Error**: Fixed Django template filter syntax in course_detail.html
- **TypeError in ExerciseDetailView**: Fixed query slicing issue causing type errors
- **Completed Lessons Count**: Fixed calculation and display of completed lessons
- **Chat API Integration**: Fixed environment variable loading for Anthropic API
- **Code Execution**: Fixed stdin input handling in RestrictedPython mode

## [1.0.0] - 2025-12-15

### Added

#### Core Features
- **Authentication System**: User registration, login, and role-based access control
- **Custom User Model**: Extended user model with student/instructor/admin roles
- **Student Profiles**: Profile with points, experience level, and streak tracking

#### Learning Class
- **Jupyter-Style Interface**: Cell-based content with text, code, image, and video support
- **Course Structure**: Organize content into courses → chapters → lessons
- **Cell Management**: Create, edit, delete, and reorder cells
- **Code Execution**: Execute Python code cells with RestrictedPython
- **Progress Tracking**: Track lesson completion and time spent

#### Training Class
- **Coding Exercises**: Create programming challenges with descriptions
- **Auto-Grading**: Automated test case execution and scoring
- **Progressive Hints**: Multi-level hint system with point penalties
- **Submission History**: Track all student submissions and attempts
- **Difficulty Levels**: Beginner, intermediate, and advanced exercises

#### Code Execution Engine
- **RestrictedPython**: Safe code execution with sandboxing
- **Security Features**: Restricted imports, no file I/O, no network access
- **Resource Limits**: Timeout controls and output truncation
- **Test Execution**: Run test cases against student code

#### User Interface
- **Responsive Design**: Bootstrap 5 with mobile-friendly layout
- **CodeMirror Editor**: Syntax highlighting for Python code
- **Markdown Support**: Rich text formatting with KaTeX for math
- **Drag-and-Drop**: SortableJS for cell reordering

### Technical Stack
- Django 5.0 web framework
- Python 3.11+
- SQLite database (development)
- Bootstrap 5 UI framework
- Alpine.js for reactive components
- HTMX for dynamic updates

---

## Version History

- **[1.1.0]** - 2026-01-23 - AI features, examination class, enhanced code execution
- **[1.0.0]** - 2025-12-15 - Initial release with learning and training classes

---

**Note**: For detailed commit history, see the Git log or GitHub releases page.
