# -*- coding: utf-8 -*-
"""
Listing – multi-line / tabulated text helper for ODF templates.

Keeps the current paragraph styling from the template while allowing
``\\n``, ``\\t``, ``\\a``, and ``\\f`` to expand into proper ODF
inline elements (``<text:line-break/>``, ``<text:tab/>``, new paragraph,
soft-page-break).

The actual XML substitution is performed by ``OdfTemplate.resolve_listing``
*after* Jinja2 rendering so that the special characters survive the render
step unchanged.

Usage::

    context = {
        "body": Listing("First line\\nSecond line\\nThird line"),
    }

In the .odt template::

    {{ body }}
"""
try:
    from html import escape
except ImportError:
    from cgi import escape  # type: ignore[no-redef]


class Listing:
    r"""Preserve newlines / tabs inside a single paragraph.

    Special characters
    ------------------
    ``\n``
        Inserts a ``<text:line-break/>`` – a soft line break *inside* the
        same paragraph.
    ``\t``
        Inserts a ``<text:tab/>`` – a tab stop.
    ``\a``
        Starts a new ``<text:p>`` paragraph (inheriting the same style as
        the surrounding paragraph).
    ``\f``
        Inserts a soft page break and then continues in a new paragraph.
    """

    def __init__(self, text) -> None:
        if not isinstance(text, (str, bytes)):
            text = str(text)
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="ignore")
        # HTML-escape the text; special control chars are preserved so that
        # OdfTemplate.resolve_listing can act on them after Jinja2 rendering.
        self.xml = escape(text)

    def __unicode__(self) -> str:
        return self.xml

    def __str__(self) -> str:
        return self.xml

    def __html__(self) -> str:
        return self.xml
