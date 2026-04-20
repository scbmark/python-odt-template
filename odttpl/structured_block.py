# -*- coding: utf-8 -*-
"""StructuredBlock — programmatic builder for mixed paragraph + nested-list ODF content.

Use cases that template-side ``{%li %}`` loops cannot express cleanly: when the
shape of the output (which paragraphs go where, which list levels exist, what
continuation paragraphs sit inside which list-items) is decided by Python logic
rather than by static template structure.

Example::

    block = StructuredBlock(tpl)
    block.add_paragraph("Findings:")
    block.add_list_item("Severity high", level=1)
    block.add_paragraph("Affected services: A, B", in_list_item=True)
    block.add_list_item("Auth service", level=2)
    block.add_list_item("Severity low", level=1)
    context = {"content": block}

In the template::

    {{block content}}

The ``{{block VAR}}`` shorthand strips the surrounding ``<text:p>`` placeholder
and substitutes the StructuredBlock's rendered XML (mixed ``<text:p>`` and
``<text:list>`` siblings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, List, Optional, Union

try:
    from html import escape
except ImportError:  # pragma: no cover - py2 fallback, unused
    from cgi import escape  # type: ignore[no-redef]

from .richtext import RichText

if TYPE_CHECKING:
    from .template import OdtTemplate


class StructuredBlockError(ValueError):
    """Raised when a StructuredBlock is built with an invalid sequence of calls."""


# ---------------------------------------------------------------------------
# List-style definition
# ---------------------------------------------------------------------------


class LabelFollowedBy(str, Enum):
    """What follows a numbered-list label in LibreOffice label-alignment mode."""

    LISTTAB = "listtab"
    TAB = "listtab"
    SPACE = "space"
    NOTHING = "nothing"
    NONE = "nothing"
    NEWLINE = "newline"
    LINEBREAK = "newline"

    def __str__(self) -> str:
        return self.value


@dataclass
class BulletLevelSpec:
    """One level of a bullet list style."""

    bullet_char: str = "\u2022"  # • (bullet)
    space_before: str = "0.5cm"
    min_label_width: str = "0.5cm"


@dataclass
class LevelSpec:
    """One level of a multi-level numbered list style.

    ``format`` accepts ODF ``style:num-format`` values:
      * ``"1"`` — arabic numerals
      * ``"a"`` / ``"A"`` — lower / upper alpha
      * ``"i"`` / ``"I"`` — lower / upper roman
      * ``"一"`` — Chinese numerals, emitted as ``"一, 二, 三, ..."``
        for LibreOffice compatibility
      * ``""`` — no numbering (plain indent)

    ``display_levels`` controls how many parent levels are concatenated into the
    label, e.g. ``display_levels=2`` at level 2 produces ``"1.1."``.

    Numbered-list positioning follows LibreOffice's label-alignment mode:
    ``first_line_indent`` maps directly to ``fo:text-indent`` (usually
    negative for hanging indents), ``indent_at`` maps to ``fo:margin-left``,
    ``label_followed_by`` accepts ``LabelFollowedBy`` values, and
    ``tab_stop_at`` sets the list tab stop when the label is followed by a tab.
    """

    format: str = "1"
    suffix: str = "."
    prefix: str = ""
    display_levels: int = 1
    first_line_indent: str = "-0.5cm"
    indent_at: str = "0.5cm"
    label_followed_by: LabelFollowedBy = LabelFollowedBy.LISTTAB
    tab_stop_at: Optional[str] = None
    start_value: int = 1


class NumberedListStyle:
    """Programmatic ``<text:list-style>`` definition, auto-registered on the template.

    On construction the style is registered into ``tpl._list_styles`` and gets a
    generated name (``odttpl_L{n}``) unless ``name`` is supplied. Pass the
    instance to ``StructuredBlock(tpl, default_list_style=...)`` or to
    ``StructuredBlock.add_list_item(..., list_style=...)``.
    """

    def __init__(
        self,
        tpl: "OdtTemplate",
        levels: List[Union[dict, LevelSpec]],
        name: Optional[str] = None,
    ) -> None:
        if not levels:
            raise StructuredBlockError("NumberedListStyle requires at least one level")
        self.tpl = tpl
        self.levels: List[LevelSpec] = [
            lvl if isinstance(lvl, LevelSpec) else LevelSpec(**lvl) for lvl in levels
        ]
        self.name = name or tpl._next_list_style_name()
        tpl._register_list_style(self)

    @property
    def xml(self) -> str:
        """Build ``<text:list-style>...</text:list-style>`` XML."""
        parts = [f'<text:list-style style:name="{self.name}">']
        for idx, spec in enumerate(self.levels, start=1):
            parts.append(self._level_xml(idx, spec))
        parts.append("</text:list-style>")
        return "".join(parts)

    @staticmethod
    def _normalize_num_format(num_format: str) -> str:
        if num_format == "一":
            return "一, 二, 三, ..."
        return num_format

    @staticmethod
    def _normalize_label_followed_by(value: LabelFollowedBy) -> str:
        if isinstance(value, LabelFollowedBy):
            return value.value
        raise StructuredBlockError(
            "label_followed_by must be a LabelFollowedBy value, "
            f"got {value!r}"
        )

    @staticmethod
    def _label_alignment_xml(spec: LevelSpec) -> str:
        followed_by = NumberedListStyle._normalize_label_followed_by(
            spec.label_followed_by
        )
        attrs = [
            f'text:label-followed-by="{followed_by}"',
            f'fo:margin-left="{escape(spec.indent_at, quote=True)}"',
            f'fo:text-indent="{escape(spec.first_line_indent, quote=True)}"',
        ]
        if followed_by == "listtab":
            tab_stop_at = spec.tab_stop_at or spec.indent_at
            attrs.append(
                f'text:list-tab-stop-position="{escape(tab_stop_at, quote=True)}"'
            )
        return "<style:list-level-label-alignment " + " ".join(attrs) + "/>"

    @staticmethod
    def _level_xml(level: int, spec: LevelSpec) -> str:
        attrs = [f'text:level="{level}"']
        if spec.format:
            num_format = NumberedListStyle._normalize_num_format(spec.format)
            attrs.append(f'style:num-format="{escape(num_format, quote=True)}"')
        else:
            attrs.append('style:num-format=""')
        if spec.prefix:
            attrs.append(f'style:num-prefix="{escape(spec.prefix, quote=True)}"')
        if spec.suffix:
            attrs.append(f'style:num-suffix="{escape(spec.suffix, quote=True)}"')
        if spec.display_levels and spec.display_levels > 1:
            attrs.append(f'text:display-levels="{spec.display_levels}"')
        if spec.start_value and spec.start_value != 1:
            attrs.append(f'text:start-value="{spec.start_value}"')
        attr_str = " ".join(attrs)
        return (
            f"<text:list-level-style-number {attr_str}>"
            "<style:list-level-properties "
            'text:list-level-position-and-space-mode="label-alignment">'
            f"{NumberedListStyle._label_alignment_xml(spec)}"
            "</style:list-level-properties>"
            "</text:list-level-style-number>"
        )


class BulletListStyle:
    """Programmatic ``<text:list-style>`` for bullet lists.

    ``levels`` accepts either ``BulletLevelSpec`` instances or plain strings
    (interpreted as the bullet character for that level with default spacing).
    """

    def __init__(
        self,
        tpl: "OdtTemplate",
        levels: List[Union[str, dict, BulletLevelSpec]],
        name: Optional[str] = None,
    ) -> None:
        if not levels:
            raise StructuredBlockError("BulletListStyle requires at least one level")
        self.tpl = tpl
        specs: List[BulletLevelSpec] = []
        for lvl in levels:
            if isinstance(lvl, BulletLevelSpec):
                specs.append(lvl)
            elif isinstance(lvl, str):
                specs.append(BulletLevelSpec(bullet_char=lvl))
            elif isinstance(lvl, dict):
                specs.append(BulletLevelSpec(**lvl))
            else:
                raise StructuredBlockError(
                    f"unsupported bullet level spec: {type(lvl)!r}"
                )
        self.levels: List[BulletLevelSpec] = specs
        self.name = name or tpl._next_list_style_name()
        tpl._register_list_style(self)

    @property
    def xml(self) -> str:
        parts = [f'<text:list-style style:name="{self.name}">']
        for idx, spec in enumerate(self.levels, start=1):
            parts.append(self._level_xml(idx, spec))
        parts.append("</text:list-style>")
        return "".join(parts)

    @staticmethod
    def _level_xml(level: int, spec: BulletLevelSpec) -> str:
        bullet = escape(spec.bullet_char, quote=True)
        return (
            f'<text:list-level-style-bullet text:level="{level}" '
            f'text:bullet-char="{bullet}">'
            "<style:list-level-properties "
            'text:list-level-position-and-space-mode="label-alignment">'
            "<style:list-level-label-alignment "
            'text:label-followed-by="listtab" '
            f'fo:margin-left="{spec.space_before}" '
            f'fo:text-indent="-{spec.min_label_width}"'
            "/>"
            "</style:list-level-properties>"
            "</text:list-level-style-bullet>"
        )


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


@dataclass
class ParagraphNode:
    text: Union[str, RichText]
    parastyle: Optional[str] = None
    in_list_item: bool = False
    margin_left: Optional[str] = None  # reserved for Phase 3
    text_indent: Optional[str] = None  # reserved for Phase 3


@dataclass
class ListItemNode:
    text: Union[str, RichText]
    level: int
    list_style: Optional[str] = None
    parastyle: Optional[str] = None
    continuation: List[ParagraphNode] = field(default_factory=list)
    nested: List["_ListGroup"] = field(default_factory=list)


@dataclass
class _ListGroup:
    """Internal: one contiguous run of items at a given level/style."""

    style_name: str
    items: List[ListItemNode] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


_BodyChild = Union[ParagraphNode, _ListGroup]


class StructuredBlock:
    """Programmatic builder for mixed paragraph / nested-list ODF content."""

    def __init__(
        self,
        tpl: "OdtTemplate",
        default_list_style: Union[str, "NumberedListStyle", "BulletListStyle", None] = None,
    ) -> None:
        self.tpl = tpl
        self._default_list_style = default_list_style
        self._default_style_obj: Optional[NumberedListStyle] = None
        self._nodes: List[_BodyChild] = []
        # _list_stack[i] is the open _ListGroup for level (i+1)
        self._list_stack: List[_ListGroup] = []
        self._current_item: Optional[ListItemNode] = None
        # List-style instances referenced by this block; re-registered on
        # every _build() call so they survive OdtTemplate.render() resets.
        self._referenced_styles: List[Any] = []
        if isinstance(default_list_style, (NumberedListStyle, BulletListStyle)):
            self._track_style(default_list_style)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_paragraph(
        self,
        text: Union[str, RichText],
        *,
        parastyle: Optional[str] = None,
        in_list_item: bool = False,
        margin_left: Optional[str] = None,
        text_indent: Optional[str] = None,
    ) -> "StructuredBlock":
        """Append a paragraph.

        If ``in_list_item`` is True, the paragraph attaches as a continuation
        paragraph inside the currently-open list-item. Otherwise any open list
        context is closed first.
        """
        node = ParagraphNode(
            text=text,
            parastyle=parastyle,
            in_list_item=in_list_item,
            margin_left=margin_left,
            text_indent=text_indent,
        )
        if in_list_item:
            if self._current_item is None:
                raise StructuredBlockError(
                    "add_paragraph(in_list_item=True) called without an open list-item"
                )
            self._current_item.continuation.append(node)
        else:
            self._close_list_context()
            self._nodes.append(node)
        return self

    def add_list_item(
        self,
        text: Union[str, RichText],
        *,
        level: int = 1,
        list_style: Union[str, "NumberedListStyle", "BulletListStyle", None] = None,
        parastyle: Optional[str] = None,
    ) -> "StructuredBlock":
        """Append a list item at the given 1-based level."""
        if level < 1:
            raise StructuredBlockError(f"level must be >= 1, got {level}")
        if level > len(self._list_stack) + 1:
            raise StructuredBlockError(
                f"level skip from {len(self._list_stack)} to {level}; "
                "intermediate levels must be added first"
            )

        if isinstance(list_style, (NumberedListStyle, BulletListStyle)):
            self._track_style(list_style)
        style_name = self._resolve_style(list_style) or self._default_style_name()

        item = ListItemNode(
            text=text,
            level=level,
            list_style=style_name,
            parastyle=parastyle,
        )

        if level == len(self._list_stack) + 1:
            # Open a new deeper level
            current_group = _ListGroup(style_name=style_name)
            if level == 1:
                self._nodes.append(current_group)
            else:
                # Nest inside current item
                assert self._current_item is not None
                self._current_item.nested.append(current_group)
            self._list_stack.append(current_group)
        else:
            # Close deeper levels
            del self._list_stack[level:]
            current_group = self._list_stack[level - 1]
            # Style change at same level → start a new sibling group
            if current_group.style_name != style_name:
                new_group = _ListGroup(style_name=style_name)
                if level == 1:
                    self._nodes.append(new_group)
                else:
                    parent_item = self._list_stack[level - 2].items[-1]
                    parent_item.nested.append(new_group)
                self._list_stack[level - 1] = new_group
                current_group = new_group

        current_group.items.append(item)
        self._current_item = item
        return self

    def close_list(self) -> "StructuredBlock":
        """Explicitly close any open list context."""
        self._close_list_context()
        return self

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _close_list_context(self) -> None:
        self._list_stack.clear()
        self._current_item = None

    def _resolve_style(
        self,
        style: Union[str, "NumberedListStyle", "BulletListStyle", None],
    ) -> Optional[str]:
        if style is None:
            return None
        if isinstance(style, str):
            return style
        if isinstance(style, (NumberedListStyle, BulletListStyle)):
            return style.name
        raise StructuredBlockError(f"unsupported list_style type: {type(style)!r}")

    def _track_style(self, style: Any) -> None:
        if style not in self._referenced_styles:
            self._referenced_styles.append(style)

    def _default_style_name(self) -> str:
        resolved = self._resolve_style(self._default_list_style)
        if resolved is not None:
            return resolved
        if self._default_style_obj is None:
            self._default_style_obj = NumberedListStyle(
                self.tpl,
                levels=[
                    LevelSpec(format="1", suffix=".", display_levels=i)
                    for i in range(1, 6)
                ],
            )
            self._track_style(self._default_style_obj)
        return self._default_style_obj.name

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_inline(self, text: Union[str, RichText]) -> str:
        if isinstance(text, RichText):
            return text._build()
        return escape(str(text))

    def _render_paragraph(self, node: ParagraphNode) -> str:
        style_name = node.parastyle
        if not style_name and (node.margin_left or node.text_indent):
            style_name = self.tpl._register_para_style(
                margin_left=node.margin_left,
                text_indent=node.text_indent,
            )
        style_attr = f' text:style-name="{style_name}"' if style_name else ""
        return f"<text:p{style_attr}>{self._render_inline(node.text)}</text:p>"

    def _render_item(self, item: ListItemNode) -> str:
        parts = [
            "<text:list-item>",
            self._render_paragraph(
                ParagraphNode(text=item.text, parastyle=item.parastyle)
            ),
        ]
        for cont in item.continuation:
            parts.append(self._render_paragraph(cont))
        for nested in item.nested:
            parts.append(self._render_group(nested, top_level=False))
        parts.append("</text:list-item>")
        return "".join(parts)

    def _render_group(self, group: _ListGroup, *, top_level: bool) -> str:
        attrs = [f'text:style-name="{group.style_name}"']
        if top_level:
            # Defensive: prevent _merge_consecutive_lists from chaining numbering
            # across unrelated blocks rendered in the same document.
            attrs.append('text:continue-numbering="false"')
        attr_str = " ".join(attrs)
        body = "".join(self._render_item(it) for it in group.items)
        return f"<text:list {attr_str}>{body}</text:list>"

    def _build(self) -> str:
        # Close any open context before rendering so the snapshot is consistent.
        self._close_list_context()
        # Re-register referenced list-styles in case OdtTemplate.render() reset
        # the registry between block construction and render time.
        for style in self._referenced_styles:
            self.tpl._register_list_style(style)
        out = []
        for node in self._nodes:
            if isinstance(node, ParagraphNode):
                out.append(self._render_paragraph(node))
            else:
                out.append(self._render_group(node, top_level=True))
        return "".join(out)

    def __str__(self) -> str:
        return self._build()

    def __html__(self) -> str:
        return self._build()


# Convenient aliases
SB = StructuredBlock
NLS = NumberedListStyle
