from .base import BaseCellHandler

class CodeCellHandler(BaseCellHandler):
    def validate(self, data):
        if 'source' not in data:
            raise ValueError("Code cell must contain 'source' field")
        return True

    def process(self, data):
        # Ensure execution count is present
        if 'execution_count' not in data:
            data['execution_count'] = 0
        return data
