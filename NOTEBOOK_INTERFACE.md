# Notebook-Style Interface（历史文档，已归档）

> ⚠️ 本文档为早期设计稿（v1.x 时代）。当前权威说明见
> [docs/DEVELOPER_MANUAL.md](docs/DEVELOPER_MANUAL.md)（§6 核心系统设计）与
> [docs/USER_MANUAL.md](docs/USER_MANUAL.md)（§3 学习课堂）。以下内容仅供参考。

This document describes the Jupyter-style notebook interface used in the Learning Platform.

## Overview

The platform uses a **cell-based content system** similar to Jupyter notebooks, allowing instructors and students to create rich, interactive lessons combining:
- Markdown text with LaTeX math
- Executable Python code
- Images with captions
- Educational videos (uploaded, embedded, or AI-generated)

## Cell Types

### 1. Text Cell
Markdown-formatted text with support for:
- Headers, lists, tables
- **Bold**, *italic*, `code` formatting
- LaTeX math equations: `$x^2 + y^2 = z^2$` or `$$\int_0^\infty e^{-x^2} dx$$`
- Links and images
- Code syntax highlighting (non-executable)

**Database Structure:**
```json
{
  "cell_type": "text",
  "data": {
    "markdown": "# Hello World\nThis is **markdown** with $\\LaTeX$ math.",
    "rendered_html": "<h1>Hello World</h1><p>This is <strong>markdown</strong>...</p>"
  }
}
```

### 2. Code Cell
Interactive Python code editor with execution capabilities:
- Syntax highlighting (CodeMirror)
- Line numbers
- Auto-completion
- Execution in sandboxed environment
- Output display (stdout, stderr, return values)
- Execution time tracking

**Database Structure:**
```json
{
  "cell_type": "code",
  "data": {
    "source": "print('Hello, World!')\nx = 5 + 3\nprint(f'Result: {x}')",
    "output": "Hello, World!\nResult: 8",
    "execution_count": 5,
    "execution_time_ms": 45,
    "status": "success"
  }
}
```

**Features:**
- Run code with Shift+Enter
- Clear output
- View execution history
- Share code snippets
- Download as .py file

### 3. Image Cell
Display images with metadata:
- Upload from local files
- Embed from URL
- AI-generated diagrams (future)
- Captions and alt text
- Responsive sizing

**Database Structure:**
```json
{
  "cell_type": "image",
  "data": {
    "url": "/media/images/2024/01/11/diagram.png",
    "caption": "Python Data Types Hierarchy",
    "alt_text": "Tree diagram showing Python's data type hierarchy",
    "width": 800,
    "height": 600
  }
}
```

### 4. Video Cell
Embed or display videos:
- **Uploaded videos**: MP4 files stored locally or S3
- **AI-generated**: Manim animations created by Video Agent
- **External**: YouTube, Vimeo embeds
- **Features**: Custom player controls, captions, playback speed

**Database Structure:**
```json
{
  "cell_type": "video",
  "data": {
    "source_type": "manim_generated",
    "url": "/media/videos/2024/01/11/list_comprehension.mp4",
    "thumbnail_url": "/media/thumbnails/list_comprehension.jpg",
    "duration_seconds": 180,
    "video_id": 123,
    "caption": "Introduction to List Comprehensions"
  }
}
```

## Cell Operations

### Frontend (JavaScript)

**Adding Cells:**
```javascript
// Add text cell after current cell
notebookEditor.addCell('text', currentIndex + 1);

// Add code cell at the end
notebookEditor.addCell('code', -1);
```

**Deleting Cells:**
```javascript
notebookEditor.deleteCell(cellIndex);
```

**Reordering Cells:**
```javascript
// Using SortableJS
new Sortable(cellContainer, {
    animation: 150,
    handle: '.cell-drag-handle',
    onEnd: function(evt) {
        notebookEditor.reorderCell(evt.oldIndex, evt.newIndex);
    }
});
```

**Executing Code:**
```javascript
async function executeCell(cellId) {
    const response = await fetch('/api/execute/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            cell_id: cellId,
            code: editor.getValue()
        })
    });
    const result = await response.json();
    displayOutput(result.output, result.status);
}
```

### Backend (Django)

**Cell Model:**
```python
class Cell(models.Model):
    CELL_TYPES = [
        ('text', 'Text/Markdown'),
        ('code', 'Code'),
        ('image', 'Image'),
        ('video', 'Video'),
    ]

    lesson = models.ForeignKey('Lesson', on_delete=models.CASCADE, related_name='cells')
    cell_type = models.CharField(max_length=20, choices=CELL_TYPES)
    order = models.PositiveIntegerField()
    data = models.JSONField()  # Cell-specific data
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['order']
        unique_together = ['lesson', 'order']

    def execute(self):
        """Execute code cell"""
        if self.cell_type != 'code':
            raise ValueError("Only code cells can be executed")

        from apps.code_runner.executor import CodeExecutor
        executor = CodeExecutor()
        result = executor.execute_code(self.data['source'])

        self.data['output'] = result['output']
        self.data['status'] = result['status']
        self.data['execution_time_ms'] = result['execution_time']
        self.save()

        return result
```

## Cell Versioning

Track edit history for undo/redo:

```python
class CellVersion(models.Model):
    cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name='versions')
    snapshot = models.JSONField()  # Complete cell state
    editor = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    change_description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
```

**Usage:**
```python
# Create version on save
def save_cell_version(cell, user, description=""):
    CellVersion.objects.create(
        cell=cell,
        snapshot={
            'cell_type': cell.cell_type,
            'data': cell.data,
            'order': cell.order
        },
        editor=user,
        change_description=description
    )

# Restore from version
def restore_cell_version(cell, version_id):
    version = CellVersion.objects.get(id=version_id)
    cell.cell_type = version.snapshot['cell_type']
    cell.data = version.snapshot['data']
    cell.order = version.snapshot['order']
    cell.save()
```

## Export/Import

### Export to Jupyter Notebook (.ipynb)

```python
def export_to_ipynb(lesson):
    """Export lesson to Jupyter notebook format"""
    notebook = {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }

    for cell in lesson.cells.all():
        if cell.cell_type == 'text':
            notebook['cells'].append({
                "cell_type": "markdown",
                "metadata": {},
                "source": [cell.data['markdown']]
            })
        elif cell.cell_type == 'code':
            notebook['cells'].append({
                "cell_type": "code",
                "execution_count": cell.data.get('execution_count'),
                "metadata": {},
                "source": [cell.data['source']],
                "outputs": [{
                    "output_type": "stream",
                    "name": "stdout",
                    "text": [cell.data.get('output', '')]
                }]
            })

    return notebook
```

### Import from Jupyter Notebook

```python
def import_from_ipynb(lesson, notebook_data):
    """Import Jupyter notebook to lesson cells"""
    for idx, nb_cell in enumerate(notebook_data['cells']):
        if nb_cell['cell_type'] == 'markdown':
            Cell.objects.create(
                lesson=lesson,
                cell_type='text',
                order=idx,
                data={
                    'markdown': ''.join(nb_cell['source']),
                    'rendered_html': ''
                }
            )
        elif nb_cell['cell_type'] == 'code':
            Cell.objects.create(
                lesson=lesson,
                cell_type='code',
                order=idx,
                data={
                    'source': ''.join(nb_cell['source']),
                    'output': '',
                    'execution_count': 0
                }
            )
```

## Frontend Components

### Notebook Editor (Alpine.js)

```html
<div x-data="notebookEditor()" class="notebook-container">
    <!-- Toolbar -->
    <div class="notebook-toolbar">
        <button @click="addCell('text')">+ Text</button>
        <button @click="addCell('code')">+ Code</button>
        <button @click="addCell('image')">+ Image</button>
        <button @click="addCell('video')">+ Video</button>
        <button @click="saveNotebook()">Save</button>
        <button @click="exportNotebook()">Export</button>
    </div>

    <!-- Cells -->
    <div id="cell-container">
        <template x-for="(cell, index) in cells" :key="cell.id">
            <div class="cell" :data-cell-id="cell.id">
                <div class="cell-drag-handle">⋮⋮</div>

                <!-- Text Cell -->
                <template x-if="cell.type === 'text'">
                    <div class="text-cell">
                        <textarea x-model="cell.data.markdown"
                                  @blur="renderMarkdown(index)"></textarea>
                        <div class="rendered" x-html="cell.data.rendered_html"></div>
                    </div>
                </template>

                <!-- Code Cell -->
                <template x-if="cell.type === 'code'">
                    <div class="code-cell">
                        <div class="code-editor" :id="'editor-' + cell.id"></div>
                        <button @click="executeCell(index)">▶ Run</button>
                        <div class="output" x-text="cell.data.output"></div>
                    </div>
                </template>

                <!-- Cell Actions -->
                <div class="cell-actions">
                    <button @click="deleteCell(index)">🗑️</button>
                    <button @click="duplicateCell(index)">📋</button>
                </div>
            </div>
        </template>
    </div>
</div>
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Shift + Enter` | Run code cell |
| `Ctrl + Enter` | Run cell, don't advance |
| `Alt + Enter` | Run cell, insert below |
| `Ctrl + S` | Save notebook |
| `Ctrl + Z` | Undo last change |
| `Ctrl + Shift + Z` | Redo |
| `A` (in command mode) | Insert cell above |
| `B` (in command mode) | Insert cell below |
| `DD` (in command mode) | Delete cell |
| `M` | Change to markdown cell |
| `Y` | Change to code cell |

## Auto-Save

Implement auto-save every 30 seconds:

```javascript
setInterval(() => {
    if (notebookEditor.hasUnsavedChanges()) {
        notebookEditor.saveNotebook(silent=true);
    }
}, 30000);
```

## Real-Time Collaboration (Future)

Enable multiple users to edit simultaneously:
- WebSocket connection for live updates
- Operational Transform for conflict resolution
- User presence indicators
- Cell-level locking during editing
- Change attribution

## Performance Optimization

1. **Lazy Rendering**: Only render visible cells
2. **Debounced Saves**: Wait 500ms after last edit before saving
3. **Cached HTML**: Store rendered markdown to avoid re-rendering
4. **Virtual Scrolling**: For notebooks with 100+ cells
5. **Code Splitting**: Load CodeMirror only for code cells

## Best Practices

1. **Cell Organization**:
   - One concept per cell
   - Keep code cells focused and small
   - Use text cells to explain code

2. **Performance**:
   - Limit output size (truncate after 1000 lines)
   - Clear output of old code cells
   - Optimize image sizes before upload

3. **Accessibility**:
   - Provide alt text for images
   - Use semantic HTML in markdown
   - Ensure keyboard navigation works

4. **Version Control**:
   - Save versions before major changes
   - Add descriptive version comments
   - Review version history regularly
