# Video Generation System

This module provides AI-powered video generation using Manim (Mathematical Animation Engine) for creating educational animations.

## Overview

The video generation system enables automatic creation of mathematical and programming animations for lessons. It uses:
- **Manim Community Edition** for rendering animations
- **AI Video Agent** to generate Manim scripts from lesson content
- **Celery** for asynchronous rendering
- **FFmpeg** for video encoding and thumbnail generation

## Architecture

### Components

1. **Manim Engine** (`manim_engine.py`)
   - Executes Manim scripts in isolated environments
   - Manages render quality settings (low/medium/high/production)
   - Handles output file management
   - Generates video metadata

2. **Script Validator** (`script_validator.py`)
   - Validates Manim Python code syntax
   - Checks for security issues (file system access, network calls)
   - Ensures required Manim imports are present
   - Validates scene class structure

3. **Scene Templates** (`templates/`)
   - Reusable Manim scene templates
   - Common animation patterns (text animations, code highlighting, diagrams)
   - Base scenes for different content types

## Usage

### Generate Video from AI

```python
from apps.ai_agents.video_agent import VideoAgent
from apps.video_generator.manim_engine import ManimEngine

# Generate Manim script using AI
agent = VideoAgent()
script = agent.generate_video_script(
    topic="Python List Comprehensions",
    difficulty="intermediate",
    duration=180  # 3 minutes
)

# Validate and render
engine = ManimEngine()
if engine.validate_script(script):
    video_path = engine.render_async(
        script=script,
        quality="medium",
        lesson_id=123
    )
```

### Manual Script Rendering

```python
from apps.video_generator.manim_engine import ManimEngine

script = '''
from manim import *

class ListComprehension(Scene):
    def construct(self):
        title = Text("List Comprehensions")
        self.play(Write(title))
        self.wait()
        # ... more animation code
'''

engine = ManimEngine()
result = engine.render(script, quality="high")
print(f"Video saved to: {result['output_path']}")
```

## Manim Script Structure

All AI-generated scripts follow this structure:

```python
from manim import *

class LessonScene(Scene):
    def construct(self):
        # 1. Introduction (5-10 seconds)
        self.intro()

        # 2. Main content (60-80% of video)
        self.main_content()

        # 3. Examples (10-20%)
        self.examples()

        # 4. Summary (5-10 seconds)
        self.summary()

    def intro(self):
        title = Text("Topic Title")
        self.play(Write(title))
        self.wait()
        self.play(FadeOut(title))

    def main_content(self):
        # Core lesson animations
        pass

    def examples(self):
        # Code examples with animations
        pass

    def summary(self):
        # Key takeaways
        pass
```

## Rendering Queue

Videos are rendered asynchronously using Celery:

```python
from apps.video_generator.tasks import render_video_task

# Queue video for rendering
task = render_video_task.delay(
    script_id=456,
    quality="medium",
    priority="normal"  # or "high" for urgent
)

# Check status
if task.ready():
    result = task.result
    video_url = result['video_url']
```

## Quality Levels

| Quality | Resolution | FPS | Bitrate | Use Case |
|---------|-----------|-----|---------|----------|
| low | 480p | 15 | 500kbps | Previews, drafts |
| medium | 720p | 30 | 2Mbps | Standard delivery |
| high | 1080p | 60 | 5Mbps | Premium content |
| production | 1080p | 60 | 10Mbps | Final export, downloads |

## Storage

### Development
- Videos stored in `media/videos/`
- Organized by date: `YYYY/MM/DD/`
- Filename: `{lesson_id}_{timestamp}_{quality}.mp4`

### Production
- Upload to S3 bucket
- Serve via CloudFront CDN
- Keep thumbnails in local cache
- Generate multiple quality versions for adaptive streaming

## Thumbnail Generation

Thumbnails are automatically generated at 10% of video duration:

```python
from apps.video_generator.manim_engine import ManimEngine

engine = ManimEngine()
thumbnail_path = engine.generate_thumbnail(
    video_path="/path/to/video.mp4",
    timestamp=3.0  # 3 seconds into video
)
```

## Security Considerations

1. **Script Validation**
   - No file system operations allowed
   - No network requests
   - No subprocess execution
   - Only Manim library imports permitted

2. **Sandboxing**
   - Manim runs in Docker container
   - Limited memory (2GB)
   - CPU quota enforced
   - Timeout after 5 minutes

3. **Resource Limits**
   - Maximum video duration: 10 minutes
   - Maximum file size: 500MB
   - Concurrent renders per user: 3
   - Queue limit: 100 pending jobs

## Error Handling

Common render failures and resolutions:

| Error | Cause | Solution |
|-------|-------|----------|
| SyntaxError | Invalid Python | Re-generate script with AI |
| ImportError | Missing Manim classes | Update script template |
| Timeout | Complex animation | Simplify scene or increase timeout |
| MemoryError | Too many objects | Reduce object count or quality |

## Monitoring

Track video generation metrics:

```python
from apps.video_generator.models import VideoRenderJob

# Check render statistics
stats = VideoRenderJob.objects.aggregate(
    total_renders=Count('id'),
    avg_render_time=Avg('render_time'),
    success_rate=Count('id', filter=Q(status='completed')) / Count('id')
)
```

## CLI Commands

```bash
# Render a specific video
python manage.py render_video --script-id 123 --quality high

# Batch render pending videos
python manage.py batch_render_videos --limit 10

# Clean up old renders
python manage.py cleanup_videos --older-than 30

# Generate thumbnail for existing video
python manage.py generate_thumbnail --video-id 456

# Test Manim installation
python manage.py test_manim
```

## Future Enhancements

- [ ] Voice narration generation (TTS)
- [ ] Interactive video elements (clickable annotations)
- [ ] Real-time preview while generating
- [ ] Video editing capabilities (trim, splice)
- [ ] Multiple aspect ratios (16:9, 9:16, 1:1)
- [ ] Subtitles/captions generation
- [ ] Video analytics (watch time, completion rate)
- [ ] Collaborative video editing
