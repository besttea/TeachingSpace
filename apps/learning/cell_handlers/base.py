class BaseCellHandler:
    """Base handler for lesson cells"""

    def validate(self, data):
        """Validate cell data structure"""
        return True

    def process(self, data):
        """Process data before saving (e.g., sanitize)"""
        return data

    def render(self, data):
        """Render cell to HTML (if needed server-side)"""
        return ""
