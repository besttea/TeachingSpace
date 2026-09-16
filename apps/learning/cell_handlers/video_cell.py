from .base import BaseCellHandler

class VideoCellHandler(BaseCellHandler):
    # The editor dropdown sends 'manim_generated' (matching Video.SOURCE_TYPES);
    # 'manim' is kept for data imported before the fix.
    VALID_SOURCES = ['youtube', 'vimeo', 'uploaded', 'manim', 'manim_generated']

    def validate(self, data):
        if 'source_type' in data and data['source_type'] not in self.VALID_SOURCES:
             raise ValueError(f"Invalid source_type. Must be one of {self.VALID_SOURCES}")
        return True
