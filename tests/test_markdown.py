import tkinter as tk
import pytest


@pytest.fixture(scope="module")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def text_widget(tk_root):
    widget = tk.Text(tk_root)
    widget.tag_configure("bold",        font=("Segoe UI", 12, "bold"))
    widget.tag_configure("italic",      font=("Segoe UI", 12, "italic"))
    widget.tag_configure("code_inline", font=("Consolas", 12), background="#f1f5f9")
    widget.tag_configure("code_block",  font=("Consolas", 12),
                         background="#1e293b", foreground="#e2e8f0")
    widget.tag_configure("heading",     font=("Segoe UI", 14, "bold"))
    yield widget
    widget.destroy()


def _get_text(widget):
    return widget.get("1.0", "end-1c")


def _tags_at(widget, index):
    return widget.tag_names(index)


def test_plain_text(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "Hello world")
    assert _get_text(text_widget) == "Hello world"


def test_bold(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "Say **hello** now")
    content = _get_text(text_widget)
    assert content == "Say hello now"
    assert "bold" in _tags_at(text_widget, "1.5")


def test_inline_code(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "Use `print()` here")
    content = _get_text(text_widget)
    assert content == "Use print() here"
    assert "code_inline" in _tags_at(text_widget, "1.5")


def test_heading(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "## My Title\nBody text")
    content = _get_text(text_widget)
    assert "My Title" in content
    assert "heading" in _tags_at(text_widget, "1.0")


def test_code_block(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "Look:\n```\nprint('hi')\n```\nDone")
    content = _get_text(text_widget)
    assert "print('hi')" in content
    assert "Done" in content
