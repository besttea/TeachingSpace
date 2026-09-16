"""
Generate a Manim video script with the Video Agent, then (optionally)
validate and render it.

Usage:
    python manage.py generate_video_script "List Comprehensions" \
        --difficulty intermediate [--render] [--quality medium] [--lesson 12]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai_agents.video_agent import VideoAgent
from apps.learning.models import Lesson, Video


class Command(BaseCommand):
    help = 'Generate (and optionally render) a Manim video script for a topic'

    def add_arguments(self, parser):
        parser.add_argument('topic', type=str, help='Topic to animate')
        parser.add_argument('--difficulty', type=str, default='intermediate',
                            choices=['beginner', 'intermediate', 'advanced'])
        parser.add_argument('--duration', type=int, default=60,
                            help='Target animation length in seconds')
        parser.add_argument('--render', action='store_true',
                            help='Render the script with Manim after validation')
        parser.add_argument('--quality', type=str, default='medium',
                            choices=['low', 'medium', 'high', 'production'])
        parser.add_argument('--lesson', type=int, default=0,
                            help='Optional lesson ID to attach the video to')

    def handle(self, *args, **options):
        topic = options['topic']
        lesson = None
        if options['lesson']:
            lesson = Lesson.objects.filter(pk=options['lesson']).first()
            if lesson is None:
                raise CommandError(f'Lesson not found: {options["lesson"]}')

        agent = VideoAgent()
        if not agent.api_key:
            raise CommandError('ANTHROPIC_API_KEY is not configured — cannot generate content')

        self.stdout.write(f'Generating Manim script for: {topic}...')
        script = agent.generate_video_script(
            topic, options['difficulty'], options['duration'])

        # Validate before doing anything else
        from apps.video_generator.script_validator import validate_script
        problems = validate_script(script)
        if problems:
            self.stdout.write(self.style.WARNING(
                'Script failed validation: ' + '; '.join(problems)))
            self.stdout.write('— script not rendered. Here it is for review:\n')
            self.stdout.write(script)
            return

        self.stdout.write(self.style.SUCCESS('Script generated and validated.'))

        video_record = Video.objects.create(
            lesson=lesson,
            title=f'{topic} 动画',
            source_type='manim_generated',
            manim_script=script,
            generation_status='pending',
        )

        if options['render']:
            from apps.video_generator.manim_engine import render_script
            self.stdout.write('Rendering with Manim (this can take minutes)...')
            result = render_script(
                script, quality=options['quality'],
                timeout=int(options['duration']) * 10 + 120)
            if result['success']:
                video_record.video_file.name = result['video_path']
                video_record.generation_status = 'completed'
                video_record.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Rendered: {result["video_path"]} ({result["duration_ms"]} ms)'))
            else:
                video_record.generation_status = 'failed'
                video_record.save()
                self.stdout.write(self.style.ERROR(f'Render failed: {result["error"]}'))
        else:
            video_record.save()
            self.stdout.write(
                f'Saved script (video id={video_record.id}, status=pending). '
                f'Render later with --render or via admin.')
