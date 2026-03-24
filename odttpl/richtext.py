# -*- coding: utf-8 -*-
"""
RichText / RichTextParagraph for ODF templates.

Unlike the DOCX version (which embeds inline ``<w:rPr>`` properties), ODF
stores text-run formatting as *named styles*.  ``RichText`` therefore keeps
a reference to the parent ``OdtTemplate`` so it can register an automatic
style on-the-fly and reference it by name from the rendered XML.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

try:
    from html import escape
except ImportError:
    from cgi import escape  # type: ignore[no-redef]

if TYPE_CHECKING:
    from .template import OdtTemplate


class RichText:
    """Build an inline rich-text fragment for use inside an existing paragraph.

    Example usage in your Python code::

        rt = RichText(tpl)
        rt.add("Hello ", bold=True)
        rt.add("world", color="#FF0000")
        context = {"greeting": rt}

    Then in your .odt template::

        {{ greeting }}

    The ``tpl`` argument must be the ``OdtTemplate`` instance so that
    automatic character styles can be registered and later injected into
    ``content.xml``.
    """

    def __init__(
        self,
        tpl: "OdtTemplate",
        text: Optional[Union[str, "RichText"]] = None,
        **text_props,
    ) -> None:
        self.tpl = tpl
        # Each entry: (escaped_text, explicit_style_name_or_None, props_dict_or_None)
        self._fragments: list = []
        if text is not None:
            self.add(text, **text_props)

    def add(
        self,
        text: Union[str, bytes, "RichText"],
        style: Optional[str] = None,
        bold: bool = False,
        italic: bool = False,
        underline: Union[bool, str] = False,
        strike: bool = False,
        color: Optional[str] = None,
        size: Optional[Union[int, float]] = None,
        font: Optional[str] = None,
        superscript: bool = False,
        subscript: bool = False,
        url_id: Optional[str] = None,
    ) -> None:
        """Append a text fragment with optional formatting.

        Parameters
        ----------
        text:
            The text (or another ``RichText``) to append.
        style:
            An existing named character style from the template document.
            When given, all other formatting keywords are ignored.
        bold / italic / underline / strike:
            Basic character properties.  ``underline`` may also be the
            underline-style string accepted by ODF (e.g. ``"solid"``,
            ``"dotted"``).
        color:
            Hex colour string, with or without the leading ``#``.
        size:
            Font size in *points* (integer or float).
        font:
            Font family name.
        superscript / subscript:
            Vertical alignment.
        url_id:
            Not used in ODF (hyperlinks are represented differently).
            Kept for API parity with the docxtpl ``RichText``.
        """
        # Merge another RichText – absorb its fragments
        if isinstance(text, RichText):
            self._fragments.extend(text._fragments)
            return

        # Coerce to str
        if not isinstance(text, str):
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="ignore")
            else:
                text = str(text)

        escaped = escape(text)

        has_props = any(
            [
                style,
                bold,
                italic,
                underline,
                strike,
                color,
                size,
                font,
                superscript,
                subscript,
            ]
        )
        if not has_props:
            self._fragments.append((escaped, None, None))
            return

        if style:
            self._fragments.append((escaped, style, None))
        else:
            props = {
                "bold": bold,
                "italic": italic,
                "underline": underline if underline else False,
                "strike": strike,
                "color": color or "",
                "size": size,
                "font": font or "",
                "superscript": superscript,
                "subscript": subscript,
            }
            self._fragments.append((escaped, None, props))

    # ------------------------------------------------------------------
    # Style names are registered lazily in _build() so that they end up
    # in tpl._auto_styles DURING Jinja2 rendering (i.e. after render()
    # resets _auto_styles at the start of each render call).
    # ------------------------------------------------------------------

    def _build(self) -> str:
        result = ""
        for escaped, explicit_style, props in self._fragments:
            if explicit_style:
                result += (
                    f'<text:span text:style-name="{explicit_style}">'
                    f"{escaped}</text:span>"
                )
            elif props:
                style_name = self.tpl._register_text_style(**props)
                result += (
                    f'<text:span text:style-name="{style_name}">{escaped}</text:span>'
                )
            else:
                result += escaped
        return result

    @property
    def xml(self) -> str:
        return self._build()

    def __unicode__(self) -> str:
        return self._build()

    def __str__(self) -> str:
        return self._build()

    def __html__(self) -> str:
        return self._build()


class RichTextParagraph:
    """Build one or more complete paragraphs for use OUTSIDE existing paragraphs.

    Example::

        rp = RichTextParagraph(tpl)
        rt = RichText(tpl, "Important", bold=True)
        rp.add(rt, parastyle="Heading_20_2")
        context = {"header": rp}

    In your template use ``{{p header }}`` (the ``p`` prefix tells odttpl to
    strip the surrounding ``<text:p>`` so that the variable replaces the whole
    paragraph rather than being inserted inside one).
    """

    def __init__(
        self,
        tpl: "OdtTemplate",
        text: Optional[Union[str, RichText]] = None,
        **text_props,
    ) -> None:
        self.tpl = tpl
        self.xml = ""
        if text is not None:
            self.add(text, **text_props)

    def add(
        self,
        text: Union[str, RichText],
        parastyle: Optional[str] = None,
    ) -> None:
        """Append a paragraph.

        Parameters
        ----------
        text:
            A ``RichText`` instance or a plain string.
        parastyle:
            Named paragraph style from the template (e.g. ``"Heading_20_1"``).
        """
        if not isinstance(text, RichText):
            text = RichText(self.tpl, text)

        style_attr = f' text:style-name="{parastyle}"' if parastyle else ""
        self.xml += f"<text:p{style_attr}>{text.xml}</text:p>"

    def __unicode__(self) -> str:
        return self.xml

    def __str__(self) -> str:
        return self.xml

    def __html__(self) -> str:
        return self.xml


# Convenient aliases matching the docxtpl naming convention
R = RichText
RP = RichTextParagraph
