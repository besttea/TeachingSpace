from .text_cell import TextCellHandler
from .code_cell import CodeCellHandler
from .image_cell import ImageCellHandler
from .video_cell import VideoCellHandler

HANDLERS = {
    'text': TextCellHandler,
    'code': CodeCellHandler,
    'image': ImageCellHandler,
    'video': VideoCellHandler,
}

def get_handler(cell_type):
    return HANDLERS.get(cell_type)()
