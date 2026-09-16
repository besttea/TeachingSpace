# Changelog

All notable changes to the Python Learning Platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-09-16

### Security
- **Sandboxed code execution rewritten**: student code runs in an isolated subprocess (default) or Docker container (`CODE_EXECUTION_BACKEND=docker` — network disabled, memory/CPU/PID limits, read-only rootfs, non-root, capabilities dropped). Strict builtins whitelist, AST private-attribute blocking, optional RestrictedPython hardening, enforced timeouts
- **XSS fixes**: json_script for cell data, `escapejs_tick` filter (backtick/`${` breakout), DOMPurify sanitization of rendered markdown, chat `innerHTML` escaping
- **Registration privilege escalation fixed** (student-only self-signup + password validators), login open-redirect fixed, logout POST-only
- **Authorization**: lesson detail/edit, cell execution (enrollment required), unpublished course/exam visibility all enforced
- Hardcoded credentials removed from management commands; API error responses sanitized (DEBUG-gated)

### Fixed
- **Grading correctness**: training submissions read the executor's real result keys (were always-passing due to `0==0`); exam code questions read `passed_tests` (were always 0 points); true/false question accessor typo fixed
- **Cell ordering**: insert/delete/reorder no longer violate the unique constraint (two-phase updates); reorder validates full permutations
- **Exams**: server-side timer enforcement (refresh no longer resets), atomic submit (no double-grading/lock-out races), attempt-number race fixed, per-attempt RNG (no global seed pollution)
- **Points system**: first-pass-only awarding (no farming), hint penalties consistent with actual hint values, atomic counter updates
- Chat history uses the most recent 20 messages; `course_detail` N+1 eliminated; slug collisions for Chinese titles; `video_cell` accepts `manim_generated`; `Enrollment.completed_at` set at 100%; prev/next lesson navigation and progress bar restored
- Production config: wsgi/asgi point to production settings, SECRET_KEY enforced, logs dir auto-created, LOGIN_REDIRECT_URL corrected

### Added
- **AI multi-provider support**: switch between Anthropic / DeepSeek / custom proxies via `AI_PROVIDER` (`deepseek_Api` env var for DeepSeek keys); agents, chat, and essay grading follow automatically
- **AI notebook tool-use**: the chat assistant queries real ClassLib materials (list/digest/section tools on the shared notebook parser) and cites sources
- **AI generation commands**: `generate_lesson` (optional notebook grounding), `generate_exercises`, `generate_exam` (drafts), `generate_video_script`, `batch_generate_content`, `test_ai_agents`
- **AI tracking & cost control**: `AIGenerationHistory` audit log, daily cost limit enforcement, response caching
- **Certificates**: PDF generation (reportlab + STSong-Light CJK), on-demand download, public verification-code page
- **Video pipeline**: Manim script validator + rendering engine (real-render verified), VideoAgent fixes
- **Celery integration**: eager-by-default task wiring with graceful fallback; grading via worker when a broker is configured
- **Cell version restore** endpoint; `export_notebook` command; pytest configuration (69 tests)

### Changed
- Requirements pruned to used dependencies and aligned with the dev environment; HTMX/CodeMirror dead CDN includes removed; TIME_ZONE=Asia/Shanghai
- Documentation: `docs/USER_MANUAL.md`, `docs/DEVELOPER_MANUAL.md`, rewritten README

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
