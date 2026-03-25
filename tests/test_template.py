# -*- coding: utf-8 -*-
"""
Basic functional tests for OdtTemplate.

Run with::

    pytest tests/
"""

import io
import os
import zipfile

from odttpl import OdtTemplate, Listing, RichText, OdtSubdoc

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


# ---------------------------------------------------------------------------
# Subdoc helpers
# ---------------------------------------------------------------------------

_CONTENT_XML_TMPL = """\
<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
    office:version="1.3">
  <office:automatic-styles>{auto_styles}</office:automatic-styles>
  <office:body>
    <office:text>{body}</office:text>
  </office:body>
</office:document-content>"""

_MANIFEST_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
                   manifest:version="1.3">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""


def _make_odt(body: str, auto_styles: str = "") -> bytes:
    """Build a minimal in-memory .odt file."""
    content = _CONTENT_XML_TMPL.format(body=body, auto_styles=auto_styles)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zf.writestr("content.xml", content.encode("utf-8"))
        zf.writestr("META-INF/manifest.xml", _MANIFEST_XML.encode("utf-8"))
    return buf.getvalue()


def _make_odt_file(tmp_path, name: str, body: str, auto_styles: str = "") -> str:
    path = str(tmp_path / name)
    with open(path, "wb") as fh:
        fh.write(_make_odt(body, auto_styles))
    return path


# ---------------------------------------------------------------------------
# Subdoc tests
# ---------------------------------------------------------------------------


def test_subdoc_basic(tmp_path):
    """Subdoc body XML is inserted into the master document."""
    master_body = '<text:p text:style-name="P1">{{p mysdoc }}</text:p>'
    master = _make_odt_file(tmp_path, "master.odt", master_body)

    sub_body = (
        '<text:p text:style-name="P1">Hello from subdoc</text:p>'
        '<text:p text:style-name="P1">Second paragraph</text:p>'
    )
    sub_path = _make_odt_file(tmp_path, "sub.odt", sub_body)

    tpl = OdtTemplate(master)
    sd = tpl.new_subdoc(sub_path)
    tpl.render({"mysdoc": sd})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    assert "Hello from subdoc" in xml
    assert "Second paragraph" in xml


def test_subdoc_auto_styles_merged(tmp_path):
    """Auto-styles from the subdoc are injected into the master's automatic-styles."""
    master_body = '<text:p text:style-name="P1">{{p mysdoc }}</text:p>'
    master = _make_odt_file(tmp_path, "master.odt", master_body)

    sub_auto_styles = (
        '<style:style style:name="P1" style:family="paragraph">'
        '<style:text-properties fo:font-weight="bold"/>'
        "</style:style>"
    )
    sub_body = '<text:p text:style-name="P1">Bold paragraph</text:p>'
    sub_path = _make_odt_file(tmp_path, "sub.odt", sub_body, sub_auto_styles)

    tpl = OdtTemplate(master)
    sd = tpl.new_subdoc(sub_path)
    tpl.render({"mysdoc": sd})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    # The renamed style should appear in automatic-styles
    assert 'fo:font-weight="bold"' in xml
    assert "Bold paragraph" in xml
    # The style name should have been prefixed
    assert 'odttpl_sd1_P1' in xml


def test_subdoc_style_name_no_collision(tmp_path):
    """Two subdocs with the same auto-style name get different prefixes."""
    master_body = (
        '<text:p text:style-name="P1">{{p sd1 }}</text:p>'
        '<text:p text:style-name="P1">{{p sd2 }}</text:p>'
    )
    master = _make_odt_file(tmp_path, "master.odt", master_body)

    common_style = (
        '<style:style style:name="P1" style:family="paragraph">'
        '<style:text-properties fo:font-weight="bold"/>'
        "</style:style>"
    )
    body1 = '<text:p text:style-name="P1">From sub1</text:p>'
    body2 = '<text:p text:style-name="P1">From sub2</text:p>'
    sub1 = _make_odt_file(tmp_path, "sub1.odt", body1, common_style)
    sub2 = _make_odt_file(tmp_path, "sub2.odt", body2, common_style)

    tpl = OdtTemplate(master)
    s1 = tpl.new_subdoc(sub1)
    s2 = tpl.new_subdoc(sub2)
    tpl.render({"sd1": s1, "sd2": s2})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    assert "From sub1" in xml
    assert "From sub2" in xml
    # Both should appear with distinct prefixes
    assert "odttpl_sd1_P1" in xml
    assert "odttpl_sd2_P1" in xml


def test_subdoc_multi_render(tmp_path):
    """Subdoc content appears correctly across multiple renders."""
    master_body = '<text:p text:style-name="P1">{{p mysdoc }}</text:p>'
    master = _make_odt_file(tmp_path, "master.odt", master_body)
    sub_auto_styles = (
        '<style:style style:name="P1" style:family="paragraph">'
        '<style:text-properties fo:font-weight="bold"/>'
        "</style:style>"
    )
    sub_body = '<text:p text:style-name="P1">Content</text:p>'
    sub_path = _make_odt_file(tmp_path, "sub.odt", sub_body, sub_auto_styles)

    tpl = OdtTemplate(master)
    sd = tpl.new_subdoc(sub_path)

    for _ in range(3):
        tpl.render({"mysdoc": sd})
        buf = io.BytesIO()
        tpl.save(buf)
        xml = _content_xml(buf.getvalue())
        assert "Content" in xml
        # prefix should always be sd1 (fresh counter each render)
        assert "odttpl_sd1_P1" in xml


def test_new_subdoc_returns_odtsubdoc(tmp_path):
    master = _make_odt_file(tmp_path, "master.odt", "<text:p/>")
    tpl = OdtTemplate(master)
    sd = tpl.new_subdoc()
    assert isinstance(sd, OdtSubdoc)
