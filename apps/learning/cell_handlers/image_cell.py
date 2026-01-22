from .base import BaseCellHandler

class ImageCellHandler(BaseCellHandler):
    def validate(self, data):
        if 'url' not in data and 'file' not in data:
            # Allow empty during creation, but warn
            pass
        return True
