# -*- coding: utf-8 -*-
"""Tests for StructuredBlock (Phase 2)."""

import io
import os
import re
import zipfile

import pytest
from lxml import etree

from odttpl import (
    OdtTemplate,
    RichText,
    StructuredBlock,
    NumberedListStyle,
    LevelSpec,
    StructuredBlockError,
)

TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _content_xml(odt_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(odt_bytes)) as zf:
        return zf.read("content.xml").decode("utf-8")


def _render(template_name: str, context: dict) -> tuple[str, OdtTemplate]:
    tpl = OdtTemplate(os.path.join(TEMPLATES, template_name))
    tpl.render(context)
    buf = io.BytesIO()
    tpl.save(buf)
    return _content_xml(buf.getvalue()), tpl


def _body(xml: str) -> str:
    """Extract the office:text body region so we can inspect generated XML
    without the surrounding document chrome."""
    m = re.search(r"<office:text>(.*?)</office:text>", xml, flags=re.DOTALL)
    return m.group(1) if m else xml


# ---------------------------------------------------------------------------
# 1. Simple paragraph only
# ---------------------------------------------------------------------------


def test_simple_paragraph_only():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_paragraph("Just one paragraph")
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    assert "<text:p>Just one paragraph</text:p>" in xml
    # The {{block}} placeholder paragraph must be stripped (only one
    # occurrence of the rendered paragraph, no lingering empty placeholder).
    assert "<text:list" not in _body(xml)


# ---------------------------------------------------------------------------
# 2. paragraph → list → paragraph, list auto-closes
# ---------------------------------------------------------------------------


def test_paragraph_then_list_then_paragraph():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_paragraph("before")
    block.add_list_item("item-1")
    block.add_list_item("item-2")
    block.add_paragraph("after")
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    body = _body(_content_xml(buf.getvalue()))

    idx_before = body.index("before")
    idx_list_open = body.index("<text:list ")
    idx_list_close = body.index("</text:list>")
    idx_after = body.index("after")
    assert idx_before < idx_list_open < idx_list_close < idx_after
    assert "item-1" in body and "item-2" in body


# ---------------------------------------------------------------------------
# 3. Three-level nested list
# ---------------------------------------------------------------------------


def test_three_level_nested_numbered_list():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("L1-a", level=1)
    block.add_list_item("L2-a", level=2)
    block.add_list_item("L3-a", level=3)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    body = _body(xml)

    # The document must be well-formed.
    etree.fromstring(xml.encode("utf-8"))

    # Three opening <text:list> tags, each for a level.
    assert body.count("<text:list ") == 3

    # Deeper lists must live INSIDE <text:list-item>, not as siblings.
    # Find the second <text:list> occurrence — the character immediately
    # before should close neither the first </text:list> nor a </text:p>
    # at the outer siblings level; it must sit inside <text:list-item>.
    first_list_open = body.index("<text:list ")
    # Second list must come after a <text:list-item> open but before its close.
    after_first = body[first_list_open:]
    second_list_rel = after_first.index("<text:list ", 1)
    between = after_first[:second_list_rel]
    # Between the first list's inner opening and the nested list, we should
    # NOT have seen a </text:list> (that would make them siblings).
    assert "</text:list>" not in between


# ---------------------------------------------------------------------------
# 4. Continuation paragraphs inside a list-item
# ---------------------------------------------------------------------------


def test_list_item_with_continuation_paragraphs():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("main text")
    block.add_paragraph("continuation one", in_list_item=True)
    block.add_paragraph("continuation two", in_list_item=True)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    body = _body(_content_xml(buf.getvalue()))

    # Extract the single <text:list-item>...</text:list-item> region.
    m = re.search(
        r"<text:list-item>(.*?)</text:list-item>", body, flags=re.DOTALL
    )
    assert m, "expected one list-item"
    item_xml = m.group(1)
    # Inside the list-item we expect three <text:p> children (main + 2 conts).
    assert item_xml.count("<text:p") == 3
    assert "main text" in item_xml
    assert "continuation one" in item_xml
    assert "continuation two" in item_xml


# ---------------------------------------------------------------------------
# 5. RichText inside a list-item registers char styles
# ---------------------------------------------------------------------------


def test_richtext_inside_list_item():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item(RichText(tpl, "bolded", bold=True))
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    assert 'fo:font-weight="bold"' in xml
    assert "bolded" in xml


# ---------------------------------------------------------------------------
# 6. RichText inside a paragraph registers char styles
# ---------------------------------------------------------------------------


def test_richtext_inside_paragraph():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_paragraph(RichText(tpl, "italicised", italic=True))
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    assert 'fo:font-style="italic"' in xml
    assert "italicised" in xml


# ---------------------------------------------------------------------------
# 7. Level skip raises
# ---------------------------------------------------------------------------


def test_level_skip_raises():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("top", level=1)
    with pytest.raises(StructuredBlockError):
        block.add_list_item("jump", level=3)


# ---------------------------------------------------------------------------
# 8. in_list_item=True without an open list raises
# ---------------------------------------------------------------------------


def test_in_list_item_without_open_list_raises():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    with pytest.raises(StructuredBlockError):
        block.add_paragraph("orphan", in_list_item=True)


# ---------------------------------------------------------------------------
# 9. Invalid level (0 / negative) raises
# ---------------------------------------------------------------------------


def test_invalid_level_raises():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    with pytest.raises(StructuredBlockError):
        block.add_list_item("x", level=0)


# ---------------------------------------------------------------------------
# 10. Default list style auto-registered
# ---------------------------------------------------------------------------


def test_default_list_style_auto_registered():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("hello")
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    # The style name should appear both in the <text:list> reference AND
    # inside <office:automatic-styles> as a <text:list-style> definition.
    assert re.search(
        r'<text:list\s+text:style-name="odttpl_L1"', xml
    ), "auto-generated style not referenced on the list"
    assert re.search(
        r'<text:list-style\s+style:name="odttpl_L1"', xml
    ), "auto-generated style not registered in automatic-styles"


# ---------------------------------------------------------------------------
# 11. Named (template-existing) list style used verbatim
# ---------------------------------------------------------------------------


def test_named_template_list_style_used_verbatim():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl, default_list_style="ExistingStyle")
    block.add_list_item("hi")
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    assert 'text:style-name="ExistingStyle"' in xml
    # No odttpl_L* generated, nothing registered under that name.
    assert "odttpl_L" not in xml
    assert 'style:name="ExistingStyle"' not in xml  # we did not define it


# ---------------------------------------------------------------------------
# 12. NumberedListStyle with custom level specs
# ---------------------------------------------------------------------------


def test_numbered_list_style_custom_levels():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    custom = NumberedListStyle(
        tpl,
        levels=[
            LevelSpec(format="A", suffix=")"),
            LevelSpec(format="1", suffix="."),
        ],
    )
    block = StructuredBlock(tpl, default_list_style=custom)
    block.add_list_item("top", level=1)
    block.add_list_item("nested", level=2)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    assert 'style:num-format="A"' in xml
    assert 'style:num-suffix=")"' in xml
    assert 'style:num-format="1"' in xml


# ---------------------------------------------------------------------------
# 13. Well-formed check after complex render
# ---------------------------------------------------------------------------


def test_well_formed_after_render():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_paragraph("Intro")
    block.add_list_item("One", level=1)
    block.add_paragraph("Note under one", in_list_item=True)
    block.add_list_item("One.a", level=2)
    block.add_list_item("One.a.i", level=3)
    block.add_list_item("Two", level=1)
    block.add_paragraph("Outro")
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    # Parsing must succeed (this is the main assertion).
    etree.fromstring(xml.encode("utf-8"))


# ---------------------------------------------------------------------------
# 14. Multiple list items in one block share the default style
# ---------------------------------------------------------------------------


def test_consecutive_blocks_share_default_style():
    """Within a single block, adding many list items that use the default
    NumberedListStyle must register the style exactly once (not once per
    list-item)."""
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    for i in range(5):
        block.add_list_item(f"row-{i}", level=1)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    # Exactly one style definition under automatic-styles.
    assert len(re.findall(r'<text:list-style\s+style:name="odttpl_L1"', xml)) == 1
    assert "odttpl_L2" not in xml


# ---------------------------------------------------------------------------
# 15. Block coexists with {%li %} shorthand in the same template
# ---------------------------------------------------------------------------


def test_block_coexists_with_li_shorthand():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block_with_li.odt"))
    block = StructuredBlock(tpl)
    block.add_paragraph("from block")
    block.add_list_item("list item from block", level=1)
    tpl.render({"content": block, "xs": ["a", "b", "c"]})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    assert "from block" in xml
    assert "list item from block" in xml
    # {%li for x in xs %} expansion
    for x in ("a", "b", "c"):
        assert f">{x}<" in xml
    etree.fromstring(xml.encode("utf-8"))


# ---------------------------------------------------------------------------
# 16. List closes when an unrelated (non-list-item) paragraph follows
# ---------------------------------------------------------------------------


def test_list_then_unrelated_paragraph_closes_list():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("inside list")
    block.add_paragraph("outside list")
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    body = _body(_content_xml(buf.getvalue()))

    idx_close = body.index("</text:list>")
    idx_outside = body.index("outside list")
    assert idx_close < idx_outside
    # The outside paragraph must NOT be nested inside any <text:list>.
    tail = body[idx_close:]
    # After the list closes, before we find "outside list", there should be
    # no further <text:list ...> opener.
    pre_outside = tail[: tail.index("outside list")]
    assert "<text:list " not in pre_outside


# ---------------------------------------------------------------------------
# 17. Paragraph margin_left creates a paragraph style — Phase 3
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Phase 3: paragraph style registration not yet implemented")
def test_paragraph_margin_left_creates_para_style():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_paragraph("indented", margin_left="2cm")
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    assert 'fo:margin-left="2cm"' in xml


# ---------------------------------------------------------------------------
# 18. Block inside a table cell — placeholder strip works there too
# ---------------------------------------------------------------------------


def test_block_inside_table_cell():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block_in_cell.odt"))
    block = StructuredBlock(tpl)
    block.add_paragraph("cell paragraph")
    block.add_list_item("cell item", level=1)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    # Content must live inside the table cell, and the XML must be well-formed.
    etree.fromstring(xml.encode("utf-8"))
    m = re.search(
        r"<table:table-cell[^>]*>(.*?)</table:table-cell>", xml, flags=re.DOTALL
    )
    assert m
    cell_inner = m.group(1)
    assert "cell paragraph" in cell_inner
    assert "cell item" in cell_inner
    assert "<text:list " in cell_inner
