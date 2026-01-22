from .base import BaseCellHandler
import markdown

class TextCellHandler(BaseCellHandler):
    def validate(self, data):
        if 'markdown' not in data:
            raise ValueError("Text cell must contain 'markdown' field")
        return True

    def process(self, data):
        # Render markdown to HTML and cache it
        md_content = data.get('markdown', '')
        # Basic markdown rendering, frontend handles KaTeX
        data['rendered_html'] = markdown.markdown(md_content, extensions=['fenced_code', 'tables'])
        return data
