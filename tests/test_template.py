# -*- coding: utf-8 -*-
"""
Basic functional tests for OdtTemplate.

Run with::

    pytest tests/
"""

import io
import os
import zipfile

from odttpl import OdtTemplate, Listing, RichText

TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")


def _content_xml(odt_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(odt_bytes)) as zf:
        return zf.read("content.xml").decode("utf-8")


def _render(template_name: str, context: dict) -> str:
    tpl = OdtTemplate(os.path.join(TEMPLATES, template_name))
    tpl.render(context)
    buf = io.BytesIO()
    tpl.save(buf)
    return _content_xml(buf.getvalue())


# ---------------------------------------------------------------------------
# Simple variable substitution
# ---------------------------------------------------------------------------


def test_simple_variable():
    xml = _render("simple_var.odt", {"name": "World"})
    assert "Hello World!" in xml


def test_variable_escaped():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "simple_var.odt"))
    tpl.render({"name": "<b>danger</b>"}, autoescape=True)
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    assert "<b>" not in xml
    assert "&lt;b&gt;" in xml


# ---------------------------------------------------------------------------
# Table row loop
# ---------------------------------------------------------------------------


def test_loop_table():
    items = [{"name": "Alpha", "value": "1"}, {"name": "Beta", "value": "2"}]
    xml = _render("loop_table.odt", {"items": items})
    assert "Alpha" in xml
    assert "Beta" in xml
    assert "1" in xml
    assert "2" in xml


# ---------------------------------------------------------------------------
# Listing (newlines / tabs)
# ---------------------------------------------------------------------------


def test_listing_newline():
    xml = _render("listing.odt", {"body": Listing("Line1\nLine2")})
    assert "<text:line-break/>" in xml


def test_listing_tab():
    xml = _render("listing.odt", {"body": Listing("col1\tcol2")})
    assert "<text:tab/>" in xml


# ---------------------------------------------------------------------------
# RichText
# ---------------------------------------------------------------------------


def test_richtext_bold():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "simple_var.odt"))
    rt = RichText(tpl, "Bold text", bold=True)
    tpl.render({"name": rt})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    # An automatic style for bold should have been injected
    assert 'fo:font-weight="bold"' in xml
    assert "Bold text" in xml


def test_richtext_color():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "simple_var.odt"))
    rt = RichText(tpl, "Coloured", color="#FF0000")
    tpl.render({"name": rt})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    assert 'fo:color="#FF0000"' in xml


def test_richtext_named_style():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "simple_var.odt"))
    rt = RichText(tpl, "Styled", style="Emphasis")
    tpl.render({"name": rt})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    assert 'text:style-name="Emphasis"' in xml


# ---------------------------------------------------------------------------
# Conditional (paragraph-level)
# ---------------------------------------------------------------------------


def test_conditional_true():
    xml = _render("conditional.odt", {"show": True})
    assert "Visible" in xml


def test_conditional_false():
    xml = _render("conditional.odt", {"show": False})
    assert "Visible" not in xml


# ---------------------------------------------------------------------------
# get_undeclared_variables
# ---------------------------------------------------------------------------


def test_undeclared_variables():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "simple_var.odt"))
    variables = tpl.get_undeclared_variables()
    assert "name" in variables


# ---------------------------------------------------------------------------
# save to file path (not just BytesIO)
# ---------------------------------------------------------------------------


def test_save_to_file(tmp_path):
    out = tmp_path / "output.odt"
    tpl = OdtTemplate(os.path.join(TEMPLATES, "simple_var.odt"))
    tpl.render({"name": "FileTest"})
    tpl.save(str(out))
    xml = _content_xml(out.read_bytes())
    assert "FileTest" in xml


# ---------------------------------------------------------------------------
# Multi-render (same OdtTemplate instance rendered twice)
# ---------------------------------------------------------------------------


def test_multi_render():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "simple_var.odt"))

    tpl.render({"name": "First"})
    buf1 = io.BytesIO()
    tpl.save(buf1)

    tpl.render({"name": "Second"})
    buf2 = io.BytesIO()
    tpl.save(buf2)

    assert "First" in _content_xml(buf1.getvalue())
    assert "Second" in _content_xml(buf2.getvalue())
    assert "First" not in _content_xml(buf2.getvalue())
