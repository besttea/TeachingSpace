from .base import BaseCellHandler

class VideoCellHandler(BaseCellHandler):
    def validate(self, data):
        valid_sources = ['youtube', 'vimeo', 'uploaded', 'manim']
        if 'source_type' in data and data['source_type'] not in valid_sources:
             raise ValueError(f"Invalid source_type. Must be one of {valid_sources}")
        return True
