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
    BulletListStyle,
    LevelSpec,
    BulletLevelSpec,
    LabelFollowedBy,
    StructuredBlockError,
)

TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")
NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
}


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


def _body_children(xml: str) -> list[etree._Element]:
    root = etree.fromstring(xml.encode("utf-8"))
    office_text = root.find(".//office:text", namespaces=NS)
    assert office_text is not None
    return [
        child
        for child in office_text
        if etree.QName(child).localname != "sequence-decls"
    ]


def _block_children(xml: str) -> list[etree._Element]:
    children = _body_children(xml)
    assert len(children) >= 2
    return children[1:-1]


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


def test_numbered_list_style_renders_libreoffice_label_alignment():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    custom = NumberedListStyle(
        tpl,
        levels=[
            LevelSpec(
                format="1",
                first_line_indent="-0.7cm",
                indent_at="1.4cm",
            ),
            LevelSpec(
                format="1",
                label_followed_by=LabelFollowedBy.SPACE,
                first_line_indent="0cm",
                indent_at="2cm",
            ),
            LevelSpec(format="1", label_followed_by=LabelFollowedBy.NOTHING),
        ],
    )
    block = StructuredBlock(tpl, default_list_style=custom)
    block.add_list_item("top", level=1)
    block.add_list_item("nested", level=2)
    block.add_list_item("deep", level=3)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    etree.fromstring(xml.encode("utf-8"))
    assert 'text:label-followed-by="listtab"' in xml
    assert 'fo:margin-left="1.4cm"' in xml
    assert 'fo:text-indent="-0.7cm"' in xml
    assert 'text:list-tab-stop-position="1.4cm"' in xml
    assert 'text:label-followed-by="space"' in xml
    assert 'fo:margin-left="2cm"' in xml
    assert 'fo:text-indent="0cm"' in xml
    assert 'text:label-followed-by="nothing"' in xml


def test_numbered_list_style_renders_custom_tab_stop():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    custom = NumberedListStyle(
        tpl,
        levels=[
            LevelSpec(
                format="1",
                label_followed_by=LabelFollowedBy.TAB,
                tab_stop_at="1.2cm",
            ),
        ],
    )
    block = StructuredBlock(tpl, default_list_style=custom)
    block.add_list_item("top", level=1)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    etree.fromstring(xml.encode("utf-8"))
    assert 'text:label-followed-by="listtab"' in xml
    assert 'text:list-tab-stop-position="1.2cm"' in xml


def test_numbered_list_style_rejects_string_label_followed_by():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    custom = NumberedListStyle(
        tpl,
        levels=[
            LevelSpec(format="1", label_followed_by="space"),
        ],
    )

    with pytest.raises(StructuredBlockError, match="LabelFollowedBy"):
        _ = custom.xml


def test_numbered_list_style_supports_chinese_numerals():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    custom = NumberedListStyle(
        tpl,
        levels=[
            LevelSpec(format="一", suffix="、"),
        ],
    )
    block = StructuredBlock(tpl, default_list_style=custom)
    block.add_list_item("top", level=1)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    etree.fromstring(xml.encode("utf-8"))
    assert 'style:num-format="一, 二, 三, ..."' in xml
    assert 'style:num-suffix="、"' in xml


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


def test_split_paragraph_resumes_nested_numbering_as_standalone_paragraph():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("L1-a", level=1)
    block.add_list_item("L2-a", level=2)
    block.add_list_item("L2-b", level=2)
    block.add_paragraph("split note", margin_left="1cm", text_indent="1cm")
    block.add_list_item("L2-c", level=2)
    block.add_list_item("L1-b", level=1)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    children = _block_children(xml)

    assert [etree.QName(child).localname for child in children] == ["list", "p", "list"]
    assert children[1].text == "split note"
    assert children[1].get(f"{{{NS['text']}}}style-name") == "odttpl_P1"
    assert children[2].get(f"{{{NS['text']}}}continue-numbering") == "true"

    resumed_items = children[2].findall("text:list-item", namespaces=NS)
    assert len(resumed_items) == 2
    assert resumed_items[0].find("text:p", namespaces=NS) is None

    resumed_nested = resumed_items[0].find("text:list", namespaces=NS)
    assert resumed_nested is not None
    assert resumed_nested.get(f"{{{NS['text']}}}continue-numbering") == "true"
    assert [
        node.findtext("text:p", namespaces=NS)
        for node in resumed_nested.findall("text:list-item", namespaces=NS)
    ] == ["L2-c"]
    assert resumed_items[1].findtext("text:p", namespaces=NS) == "L1-b"

    style_match = re.search(
        r'<style:style\s+style:name="odttpl_P1"\s+style:family="paragraph"(.*?)</style:style>',
        xml,
        flags=re.DOTALL,
    )
    assert style_match is not None
    assert "style:list-style-name" not in style_match.group(0)


def test_split_paragraph_can_restart_numbering_without_resuming():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("L1-a", level=1)
    block.add_list_item("L2-a", level=2)
    block.add_paragraph("split note")
    block.add_list_item("L2-b", level=2, continue_numbering=False)
    block.add_list_item("L1-b", level=1)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    children = _block_children(xml)

    assert [etree.QName(child).localname for child in children] == ["list", "p", "list"]
    assert children[2].get(f"{{{NS['text']}}}continue-numbering") == "true"
    resumed_items = children[2].findall("text:list-item", namespaces=NS)
    assert len(resumed_items) == 2
    assert resumed_items[0].find("text:p", namespaces=NS) is None
    resumed_nested = children[2].find("text:list-item/text:list", namespaces=NS)
    assert resumed_nested is not None
    assert resumed_nested.get(f"{{{NS['text']}}}continue-numbering") == "false"
    assert resumed_nested.findtext("text:list-item/text:p", namespaces=NS) == "L2-b"
    assert resumed_items[1].findtext("text:p", namespaces=NS) == "L1-b"


def test_multiple_split_paragraphs_preserve_resumable_context():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("L1-a", level=1)
    block.add_list_item("L2-a", level=2)
    block.add_paragraph("split one")
    block.add_paragraph("split two")
    block.add_list_item("L2-b", level=2)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    children = _block_children(xml)

    assert [etree.QName(child).localname for child in children] == [
        "list",
        "p",
        "p",
        "list",
    ]
    assert [child.text for child in children[1:3]] == ["split one", "split two"]
    assert children[3].get(f"{{{NS['text']}}}continue-numbering") == "true"
    assert (
        children[3]
        .find("text:list-item/text:list", namespaces=NS)
        .get(f"{{{NS['text']}}}continue-numbering")
        == "true"
    )


def test_live_nested_restart_starts_new_sibling_segment():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("L1-a", level=1)
    block.add_list_item("L2-a", level=2)
    block.add_list_item("L2-b", level=2)
    block.add_list_item("L2-c", level=2, continue_numbering=False)
    block.add_list_item("L2-d", level=2)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    children = _block_children(xml)

    assert [etree.QName(child).localname for child in children] == ["list"]
    top_items = children[0].findall("text:list-item", namespaces=NS)
    assert len(top_items) == 1
    nested_lists = top_items[0].findall("text:list", namespaces=NS)
    assert len(nested_lists) == 2
    assert [
        [
            node.findtext("text:p", namespaces=NS)
            for node in nested.findall("text:list-item", namespaces=NS)
        ]
        for nested in nested_lists
    ] == [["L2-a", "L2-b"], ["L2-c", "L2-d"]]
    assert nested_lists[1].get(f"{{{NS['text']}}}continue-numbering") == "false"


def test_live_top_level_restart_starts_new_top_level_segment():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("L1-a", level=1)
    block.add_list_item("L2-a", level=2)
    block.add_list_item("L1-b", level=1, continue_numbering=False)
    block.add_list_item("L1-c", level=1)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    children = _block_children(xml)

    assert [etree.QName(child).localname for child in children] == ["list", "list"]
    assert children[0].get(f"{{{NS['text']}}}continue-numbering") == "false"
    assert children[1].get(f"{{{NS['text']}}}continue-numbering") == "false"
    assert [
        node.findtext("text:p", namespaces=NS)
        for node in children[1].findall("text:list-item", namespaces=NS)
    ] == ["L1-b", "L1-c"]


def test_close_list_clears_suspended_resumable_context():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("L1-a", level=1)
    block.add_list_item("L2-a", level=2)
    block.add_paragraph("split note")
    block.close_list()

    with pytest.raises(StructuredBlockError):
        block.add_list_item("L2-b", level=2)


def test_continue_numbering_true_requires_suspended_context():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)

    with pytest.raises(StructuredBlockError, match="continue_numbering=True"):
        block.add_list_item("L1-a", level=1, continue_numbering=True)


def test_in_list_item_continuation_para_style_has_no_list_style_name():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_list_item("main", level=1)
    block.add_paragraph(
        "continuation",
        in_list_item=True,
        margin_left="1cm",
        text_indent="1cm",
    )
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())
    body = _body(xml)

    m = re.search(
        r"<text:list-item>(.*?)</text:list-item>",
        body,
        flags=re.DOTALL,
    )
    assert m is not None
    item_xml = m.group(1)
    assert item_xml.count("<text:p") == 2
    assert "continuation" in item_xml

    style_match = re.search(
        r'<style:style\s+style:name="odttpl_P1"\s+style:family="paragraph"(.*?)</style:style>',
        xml,
        flags=re.DOTALL,
    )
    assert style_match is not None
    assert "style:list-style-name" not in style_match.group(0)


def test_paragraph_margin_left_creates_para_style():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    block = StructuredBlock(tpl)
    block.add_paragraph("indented", margin_left="2cm", text_indent="-0.5cm")
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    # Auto-generated paragraph style is registered AND referenced.
    assert 'fo:margin-left="2cm"' in xml
    assert 'fo:text-indent="-0.5cm"' in xml
    assert re.search(
        r'<style:style\s+style:name="odttpl_P1"\s+style:family="paragraph"', xml
    )
    assert re.search(r'<text:p\s+text:style-name="odttpl_P1"', xml)


# ---------------------------------------------------------------------------
# 19. BulletListStyle — bullet chars rendered as list-level-style-bullet
# ---------------------------------------------------------------------------


def test_bullet_list_style_renders_bullets():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    bullets = BulletListStyle(tpl, levels=["\u2022", "\u25e6"])
    block = StructuredBlock(tpl, default_list_style=bullets)
    block.add_list_item("first", level=1)
    block.add_list_item("second", level=2)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    etree.fromstring(xml.encode("utf-8"))
    assert "<text:list-level-style-bullet " in xml
    assert 'text:bullet-char="\u2022"' in xml
    assert 'text:bullet-char="\u25e6"' in xml


def test_bullet_list_style_accepts_spec_and_dict():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    bullets = BulletListStyle(
        tpl,
        levels=[
            BulletLevelSpec(bullet_char="-", space_before="1cm"),
            {"bullet_char": "*", "min_label_width": "0.3cm"},
        ],
    )
    block = StructuredBlock(tpl, default_list_style=bullets)
    block.add_list_item("a", level=1)
    block.add_list_item("b", level=2)
    tpl.render({"content": block})
    buf = io.BytesIO()
    tpl.save(buf)
    xml = _content_xml(buf.getvalue())

    etree.fromstring(xml.encode("utf-8"))
    assert 'text:bullet-char="-"' in xml
    assert 'text:bullet-char="*"' in xml
    assert 'fo:margin-left="1cm"' in xml


def test_bullet_list_style_empty_raises():
    tpl = OdtTemplate(os.path.join(TEMPLATES, "structured_block.odt"))
    with pytest.raises(StructuredBlockError):
        BulletListStyle(tpl, levels=[])


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
