"""
Clean up stale video artifacts (T21).

Usage:
    python manage.py cleanup_videos --older-than 30 [--dry-run]
    python manage.py cleanup_videos --failed-only   # remove failed Video records

Removes: failed Video records older than N days, and video files under
media/videos not referenced by any Video record (orphans).
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.learning.models import Video


class Command(BaseCommand):
    help = '清理过期的视频渲染产物与失败记录'

    def add_arguments(self, parser):
        parser.add_argument('--older-than', type=int, default=30,
                            help='清理 N 天前的失败记录（默认 30）')
        parser.add_argument('--dry-run', action='store_true',
                            help='只报告，不删除')

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['older_than'])
        removed = 0

        # 1) failed records older than N days
        failed = Video.objects.filter(
            generation_status='failed', created_at__lt=cutoff)
        self.stdout.write(f'过期失败记录: {failed.count()} 条')
        if not options['dry_run']:
            removed += failed.count()
            failed.delete()

        # 2) orphan video files not referenced by any Video record
        referenced = set(
            (v.video_file.name or '') for v in Video.objects.exclude(video_file='')
        )
        videos_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
        orphan_count = 0
        if os.path.isdir(videos_dir):
            for root, _dirs, files in os.walk(videos_dir):
                for name in files:
                    path = os.path.join(root, name)
                    rel = os.path.relpath(path, settings.MEDIA_ROOT).replace('\\', '/')
                    if rel not in referenced:
                        orphan_count += 1
                        if not options['dry_run']:
                            os.remove(path)
        self.stdout.write(f'孤儿视频文件: {orphan_count} 个')

        self.stdout.write(self.style.SUCCESS(
            f'{"（干跑）" if options["dry_run"] else ""}完成：'
            f'删除 {removed} 条失败记录、{orphan_count} 个孤儿文件'))
