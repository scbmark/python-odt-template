# -*- coding: utf-8 -*-
"""
ODF template engine – modelled after python-docx-template.

An .odt/.ods/.odp file is a ZIP archive; the main text content lives in
content.xml and page-level styles/headers/footers live in styles.xml.
Both files are patched so that Jinja2 can render them, then written back
into a new ZIP archive.
"""

from __future__ import annotations

import binascii
import hashlib
import io
import os
import re
import zipfile
from typing import Any, Dict, IO, Optional, Set, Union
from pathlib import Path

from lxml import etree  # ty:ignore[unresolved-import]
from jinja2 import Environment, Template, meta
from jinja2.exceptions import TemplateError

from .subdoc import OdtSubdoc

try:
    from html import escape
except ImportError:
    from cgi import escape  # type: ignore[no-redef]  # noqa: F401

# ---------------------------------------------------------------------------
# MIME type guessing for images
# ---------------------------------------------------------------------------
_EXT_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "svg": "image/svg+xml",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "webp": "image/webp",
}


def _mime_for_ext(ext: str) -> str:
    return _EXT_MIME.get(ext.lower().lstrip("."), "application/octet-stream")


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class OdtTemplate:
    """Treat an ODF file (.odt, .ods, .odp …) as a Jinja2 template.

    Usage::

        tpl = OdtTemplate("my_template.odt")
        tpl.render({"name": "World", "rows": [...]})
        tpl.save("output.odt")
    """

    def __init__(self, template_file: Union[str, Path, IO[bytes]]) -> None:
        self.template_file = template_file
        self._template_data: Optional[bytes] = None
        # filename → bytes for files that were modified or added during render
        self._modified_files: Dict[str, bytes] = {}
        # extra image files to embed: image filename → bytes
        self._extra_images: Dict[str, bytes] = {}
        # automatic text-style registry: frozenset(props) → style_name
        self._auto_styles: Dict[frozenset, str] = {}
        self.is_rendered = False
        # subdoc tracking (reset on each render)
        self._subdoc_list: list = []
        self._subdoc_counter: int = 1

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_template(self) -> None:
        if self._template_data is None:
            if hasattr(self.template_file, "read"):
                self._template_data = self.template_file.read()  # type: ignore[union-attr]
            else:
                with open(self.template_file, "rb") as fh:
                    self._template_data = fh.read()

    def _read_zip_entry(self, filename: str) -> str:
        self._load_template()
        with zipfile.ZipFile(io.BytesIO(self._template_data)) as zf:  # ty:ignore[invalid-argument-type]
            return zf.read(filename).decode("utf-8")

    def _has_zip_entry(self, filename: str) -> bool:
        self._load_template()
        with zipfile.ZipFile(io.BytesIO(self._template_data)) as zf:  # ty:ignore[invalid-argument-type]
            return filename in zf.namelist()

    # ------------------------------------------------------------------
    # Public XML accessors
    # ------------------------------------------------------------------

    def get_content_xml(self) -> str:
        return self._read_zip_entry("content.xml")

    def get_styles_xml(self) -> str:
        return self._read_zip_entry("styles.xml")

    def xml_to_string(self, element: etree._Element) -> str:
        return etree.tostring(element, encoding="unicode", pretty_print=False)

    def write_content_xml(self, filename: str) -> None:
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(self.get_content_xml())

    # ------------------------------------------------------------------
    # XML patching – make ODF XML digestible by Jinja2
    # ------------------------------------------------------------------

    def patch_xml(self, src_xml: str) -> str:
        """Clean up an ODF XML string so that Jinja2 can parse it.

        LibreOffice / OpenOffice may split a single Jinja2 tag like
        ``{{ variable }}`` across several ``<text:span>`` elements.  This
        method stitches those fragments back together so that the tag is
        presented as a single, unbroken string to Jinja2.

        Special shorthands (mirrors docxtpl):

        * ``{%tr ... %}``  → controls a ``<table:table-row>`` element
        * ``{%tc ... %}``  → controls a ``<table:table-cell>`` element
        * ``{%p  ... %}``  → controls a ``<text:p>`` element
        * ``{%s  ... %}``  → controls a ``<text:span>`` element

        The corresponding ``{{ tr … }}`` / ``{{ tc … }}`` / ``{{ p … }}`` /
        ``{{ s … }}`` shorthands are also supported for expressions.
        """

        # ----------------------------------------------------------------
        # Step 1 – remove stray XML tags immediately adjacent to {{ / {%
        # e.g.  {<w:r>{ → {{
        # ----------------------------------------------------------------
        src_xml = re.sub(
            r"(?<={)(<[^>]*>)+(?=[\{%\#])|(?<=[%\}\#])(<[^>]*>)+(?=\})",
            "",
            src_xml,
            flags=re.DOTALL,
        )

        # ----------------------------------------------------------------
        # Step 2 – remove </text:span>…<text:span…> boundaries that appear
        # INSIDE a Jinja2 block (i.e. OO/LO split the tag across spans)
        # ----------------------------------------------------------------
        def _striptags(m: re.Match) -> str:
            # Remove all inline XML tags inside the Jinja2 block while
            # preserving text content.  A previous approach used
            # `</text:span>.*?<text:span[^>]*>` first, but that pattern
            # inadvertently consumed text nodes between span boundaries
            # (e.g. `{{p sub }}` split by LO as
            # `{<span>{</span>p sub <span>}</span>}` would lose `p sub`).
            return re.sub(r"<[^>]+>", "", m.group(0))

        src_xml = re.sub(
            r"{%(?:(?!%}).)*|{#(?:(?!#}).)*|{{(?:(?!}}).)*",
            _striptags,
            src_xml,
            flags=re.DOTALL,
        )

        # ----------------------------------------------------------------
        # Step 3 – handle {%tr/%tc/%p/%s and {{tr/{{tc/{{p/{{s shorthands:
        # strip the surrounding ODF element so that Jinja2 controls the
        # repetition / conditional at the right XML nesting level.
        # ----------------------------------------------------------------
        _TAG_MAP = [
            ("tr", "table:table-row"),
            ("tc", "table:table-cell"),
            ("p", "text:p"),
            ("s", "text:span"),
        ]
        for y, tag in _TAG_MAP:
            # {%y ... %} and {{y ... }} (expression)
            pat = (
                r"<%(tag)s[ >](?:(?!<%(tag)s[ >]).)*"
                r"({%%|{{)%(y)s ([^}%%]*(?:%%}|}})).*?</%(tag)s>" % {"tag": tag, "y": y}
            )
            src_xml = re.sub(pat, r"\1 \2", src_xml, flags=re.DOTALL)

        # {#y ... #} comment blocks (no span, only tr/tc/p)
        for y, tag in _TAG_MAP[:3]:
            pat = (
                r"<%(tag)s[ >](?:(?!<%(tag)s[ >]).)*"
                r"({#)%(y)s ([^}#]*(?:#})).*?</%(tag)s>" % {"tag": tag, "y": y}
            )
            src_xml = re.sub(pat, r"\1 \2", src_xml, flags=re.DOTALL)

        # ----------------------------------------------------------------
        # Step 4 – {%- / -%} whitespace trimming: merge with adjacent text
        # ----------------------------------------------------------------
        src_xml = re.sub(
            r"</text:span>(?:(?!</text:span>).)*?{%-",
            "{%",
            src_xml,
            flags=re.DOTALL,
        )
        src_xml = re.sub(
            r"-%}(?:(?!<text:span|{%|{{).)*?<text:span[^>]*>",
            "%}",
            src_xml,
            flags=re.DOTALL,
        )

        # ----------------------------------------------------------------
        # Step 5 – remove orphaned </text:span> closing tags that were left
        # behind when patch_xml Step 1 removed the matching opening <text:span>
        # (happens when LO stores {% as bare "{" + <span>% ...)
        # ----------------------------------------------------------------
        src_xml = self._remove_orphaned_close_spans(src_xml)

        # ----------------------------------------------------------------
        # Step 6 – unescape HTML entities/smart-quotes inside {{ … }} / {% … %}
        # ----------------------------------------------------------------
        def _clean_tags(m: re.Match) -> str:
            # Order matters: &amp; must be unescaped LAST so that literal
            # "&quot;" in source (encoded as "&amp;quot;") is not double-decoded.
            return (
                m.group(0)
                .replace("&#8216;", "'")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
                .replace("&apos;", "'")
                .replace("&#160;", " ")
                .replace("&nbsp;", " ")
                .replace("\u201c", '"')
                .replace("\u201d", '"')
                .replace("\u2018", "'")
                .replace("\u2019", "'")
                .replace("&amp;", "&")
            )

        src_xml = re.sub(r"(?<=\{[\{%])(.*?)(?=[\}%]})", _clean_tags, src_xml)

        return src_xml

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render_xml_part(
        self,
        src_xml: str,
        context: Dict[str, Any],
        jinja_env: Optional[Environment] = None,
    ) -> str:
        # Insert newlines before <text:p> so that Jinja2 line numbers are
        # useful for error reporting.
        src_xml = re.sub(r"<text:p([ >])", r"\n<text:p\1", src_xml)
        try:
            if jinja_env:
                template = jinja_env.from_string(src_xml)
            else:
                template = Template(src_xml)
            dst_xml = template.render(context)
        except TemplateError as exc:
            if hasattr(exc, "lineno") and exc.lineno is not None:
                line_number = max(exc.lineno - 4, 0)  # ty:ignore[unsupported-operator]
                exc.odf_context = list(  # type: ignore[attr-defined]
                    map(
                        lambda x: re.sub(r"<[^>]+>", "", x),
                        src_xml.splitlines()[line_number : line_number + 7],
                    )
                )
            raise
        dst_xml = re.sub(r"\n<text:p([ >])", r"<text:p\1", dst_xml)
        # Restore escaped jinja2 literals {_{ … }_}  /  {_% … %_}
        dst_xml = (
            dst_xml.replace("{_{", "{{")
            .replace("}_}", "}}")
            .replace("{_%", "{%")
            .replace("%_}", "%}")
        )
        dst_xml = self.resolve_listing(dst_xml)
        dst_xml = self._merge_consecutive_lists(dst_xml)
        dst_xml = self._remove_orphaned_close_spans(dst_xml)
        return dst_xml

    # ------------------------------------------------------------------
    # Orphaned span cleanup – shared by patch_xml and render_xml_part
    # ------------------------------------------------------------------

    @staticmethod
    def _remove_orphaned_close_spans(xml: str) -> str:
        """Remove ``</text:span>`` closing tags that have no matching opener.

        LibreOffice sometimes stores Jinja2 tags split across ``<text:span>``
        elements.  After ``patch_xml`` strips the stray XML inside those tags
        some closing ``</text:span>`` tags are left without a corresponding
        opener.  The same situation arises after Jinja2 *renders* a ``{% for %}``
        loop that begins inside a nested span: each iteration's loop body starts
        with the closing tags of those surrounding spans, which are orphaned for
        every iteration after the first.

        Strategy: track ``<text:span>`` open/close depth.  A ``</text:span>``
        that arrives when depth == 0 has no matching opener and is discarded.
        The depth is also reset to 0 at each paragraph boundary so that a
        malformed paragraph cannot corrupt subsequent paragraphs.
        """
        parts = re.split(
            r"(<text:span(?:\s[^>]*)?>|<text:span\s*/>|</text:span>"
            r"|<text:p(?:\s[^>]*)?>|</text:p>)",
            xml,
        )
        depth = 0
        cleaned: list[str] = []
        for part in parts:
            if re.fullmatch(r"<text:span(?:\s[^>]*)?>", part):
                depth += 1
                cleaned.append(part)
            elif re.fullmatch(r"<text:span\s*/>", part):
                cleaned.append(part)  # self-closing, depth unchanged
            elif part == "</text:span>":
                if depth > 0:
                    depth -= 1
                    cleaned.append(part)
                # else: orphaned closing tag — discard
            elif re.fullmatch(r"<text:p(?:\s[^>]*)?>", part) or part == "</text:p>":
                # Spans must not cross paragraph boundaries; reset depth.
                depth = 0
                cleaned.append(part)
            else:
                cleaned.append(part)
        return "".join(cleaned)

    # ------------------------------------------------------------------
    # List merging – fix auto-numbering after for-loop expansion
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_consecutive_lists(xml: str) -> str:
        """Merge consecutive ``<text:list>`` elements that share the same style.

        When a Jinja2 ``{% for %}`` loop expands inside a list item, each
        iteration produces its own ``<text:list>`` wrapper, so every item
        restarts numbering at 1.  Merging adjacent same-style lists into one
        restores correct auto-numbering.

        Handles arbitrary nesting: only *outer-level* (depth-0) lists are
        candidates for merging; inner lists are left untouched.
        """
        _LIST_OPEN = re.compile(r"<text:list\b(?:\s[^>]*)?>", re.DOTALL)
        _STYLE = re.compile(r'\btext:style-name="([^"]*)"')

        # Tokenise on list open/close tags only.
        tokens = re.split(r"(<text:list\b(?:\s[^>]*)?>|</text:list>)", xml)

        result: list[str] = []
        depth = 0
        style_stack: list[str] = []
        # Style name of the most-recently-closed outer list (buffered close tag).
        pending_close_style: Optional[str] = None

        for token in tokens:
            if _LIST_OPEN.fullmatch(token):
                sm = _STYLE.search(token)
                style = sm.group(1) if sm else ""

                if (
                    pending_close_style is not None
                    and depth == 0
                    and style == pending_close_style
                ):
                    # Adjacent same-style list at the outer level → merge:
                    # drop both the buffered </text:list> and this opening tag.
                    pending_close_style = None
                else:
                    if pending_close_style is not None:
                        # Different style or different depth — flush the buffered close.
                        result.append("</text:list>")
                        pending_close_style = None
                    result.append(token)

                style_stack.append(style)
                depth += 1

            elif token == "</text:list>":
                depth -= 1
                closed_style = style_stack.pop() if style_stack else ""

                if depth == 0:
                    # Buffer so we can peek at the next sibling list.
                    if pending_close_style is not None:
                        result.append("</text:list>")
                    pending_close_style = closed_style
                else:
                    # Inner close tag — emit immediately.
                    if pending_close_style is not None:
                        result.append("</text:list>")
                        pending_close_style = None
                    result.append(token)

            else:
                # Non-list-tag content.
                if pending_close_style is not None and token.strip():
                    # Real content between lists — flush the buffered close.
                    result.append("</text:list>")
                    pending_close_style = None
                result.append(token)

        if pending_close_style is not None:
            result.append("</text:list>")

        return "".join(result)

    # ------------------------------------------------------------------
    # Listing resolution – convert \n / \t / \a / \f to ODF XML
    # ------------------------------------------------------------------

    def resolve_listing(self, xml: str) -> str:
        """Replace special characters produced by ``Listing`` objects with
        the appropriate ODF inline elements.

        * ``\\n``  → ``<text:line-break/>``
        * ``\\t``  → ``<text:tab/>``
        * ``\\a``  → new paragraph (closes / reopens ``<text:p>``)
        * ``\\f``  → soft page break
        """

        _SPECIAL = frozenset("\n\t\a\f")

        def _fix_text(text: str, para_attrs: str) -> str:
            """Convert special chars in a single text node to ODF elements."""
            text = text.replace("\t", "<text:tab/>")
            text = text.replace(
                "\a",
                f"</text:p><text:p{para_attrs}>",
            )
            text = text.replace(
                "\f",
                f"</text:p><text:p><text:soft-page-break/></text:p>"
                f"<text:p{para_attrs}>",
            )
            text = text.replace("\n", "<text:line-break/>")
            return text

        def _maybe_fix(text: str, para_attrs: str) -> str:
            """Only apply _fix_text when the node actually contains special chars."""
            if text.strip() and _SPECIAL.intersection(text):
                return _fix_text(text, para_attrs)
            return text

        def _resolve_para(m: re.Match) -> str:
            full = m.group(0)
            para_attrs_m = re.match(r"<text:p([^>]*)>", full)
            para_attrs = para_attrs_m.group(1) if para_attrs_m else ""
            # Replace text nodes (both inside <text:span> and bare in <text:p>)
            return re.sub(
                r"(?<=>)([^<]+)(?=<)",
                lambda x: _maybe_fix(x.group(0), para_attrs),
                full,
            )

        xml = re.sub(
            r"<text:p[^>]*>.*?</text:p>",
            _resolve_para,
            xml,
            flags=re.DOTALL,
        )
        return xml

    # ------------------------------------------------------------------
    # Build rendered XML for each part
    # ------------------------------------------------------------------

    def build_content_xml(
        self,
        context: Dict[str, Any],
        jinja_env: Optional[Environment] = None,
    ) -> str:
        xml = self.get_content_xml()
        xml = self.patch_xml(xml)
        xml = self.render_xml_part(xml, context, jinja_env)
        return xml

    def build_styles_xml(
        self,
        context: Dict[str, Any],
        jinja_env: Optional[Environment] = None,
    ) -> str:
        xml = self.get_styles_xml()
        xml = self.patch_xml(xml)
        xml = self.render_xml_part(xml, context, jinja_env)
        return xml

    # ------------------------------------------------------------------
    # Automatic style management (for RichText)
    # ------------------------------------------------------------------

    def _register_text_style(self, **props: Any) -> str:
        """Register a text automatic style and return its generated name."""
        key: frozenset = frozenset((k, v) for k, v in props.items() if v)
        if key not in self._auto_styles:
            self._auto_styles[key] = f"odttpl_T{len(self._auto_styles) + 1}"
        return self._auto_styles[key]

    def _build_auto_styles_xml(self) -> str:
        """Return XML fragments for all registered automatic text styles."""
        parts = []
        for key, name in self._auto_styles.items():
            props = dict(key)
            tp: list[str] = []
            if props.get("bold"):
                tp.append(
                    'fo:font-weight="bold" fo:font-weight-asian="bold" fo:font-weight-complex="bold"'
                )
            if props.get("italic"):
                tp.append(
                    'fo:font-style="italic" fo:font-style-asian="italic" fo:font-style-complex="italic"'
                )
            if props.get("underline"):
                u = props["underline"]
                u_style = u if isinstance(u, str) and u != "single" else "solid"
                tp.append(
                    f'style:text-underline-style="{u_style}" '
                    'style:text-underline-width="auto" '
                    'style:text-underline-color="font-color"'
                )
            if props.get("strike"):
                tp.append('style:text-line-through-style="solid"')
            if props.get("color"):
                color = props["color"]
                if not color.startswith("#"):
                    color = "#" + color
                tp.append(f'fo:color="{color}"')
            if props.get("size"):
                s = props["size"]
                tp.append(
                    f'fo:font-size="{s}pt" style:font-size-asian="{s}pt" style:font-size-complex="{s}pt"'
                )
            if props.get("font"):
                f = props["font"]
                tp.append(
                    f'fo:font-family="{f}" style:font-family-asian="{f}" style:font-family-complex="{f}"'
                )
            if props.get("superscript"):
                tp.append('style:text-position="super 58%"')
            if props.get("subscript"):
                tp.append('style:text-position="sub 58%"')
            tp_str = " ".join(tp)
            parts.append(
                f'<style:style style:name="{name}" style:family="text">'
                f"<style:text-properties {tp_str}/>"
                f"</style:style>"
            )
        return "".join(parts)

    def _inject_auto_styles(self, content_xml: str) -> str:
        """Inject automatic text styles into content.xml.

        Handles both the self-closing form ``<office:automatic-styles/>``
        and the expanded form ``<office:automatic-styles>…</office:automatic-styles>``.
        """
        styles_xml = self._build_auto_styles_xml()
        if not styles_xml:
            return content_xml
        # Self-closing form → expand and inject
        content_xml = re.sub(
            r"<office:automatic-styles\s*/>",
            f"<office:automatic-styles>{styles_xml}</office:automatic-styles>",
            content_xml,
        )
        # Expanded form → insert before closing tag
        content_xml = content_xml.replace(
            "</office:automatic-styles>",
            styles_xml + "</office:automatic-styles>",
        )
        return content_xml

    # ------------------------------------------------------------------
    # Subdoc management
    # ------------------------------------------------------------------

    def new_subdoc(self, odt_path: Optional[str] = None) -> OdtSubdoc:
        """Create a new :class:`OdtSubdoc` associated with this template.

        *odt_path* – optional path to an existing ``.odt`` file whose body
        will be merged into the master document at render time.

        Example::

            sd = tpl.new_subdoc("chapter.odt")
            tpl.render({"chapter": sd})

        In the template use ``{%p chapter %}`` for block-level insertion.
        """
        return OdtSubdoc(self, odt_path)

    def _register_subdoc(self, subdoc: OdtSubdoc) -> None:
        """Register a subdoc so its styles and images are merged at render time."""
        if subdoc not in self._subdoc_list:
            self._subdoc_list.append(subdoc)

    # ------------------------------------------------------------------
    # Image management (for InlineImage)
    # ------------------------------------------------------------------

    def _add_image(self, image_descriptor: Union[str, Path, IO[bytes]]) -> str:
        """Store image bytes and return the picture filename (no path prefix)."""
        if hasattr(image_descriptor, "read"):
            image_data: bytes = image_descriptor.read()  # type: ignore[union-attr]
            ext = getattr(image_descriptor, "name", "image.png")
            ext = os.path.splitext(str(ext))[1].lstrip(".")
        else:
            with open(image_descriptor, "rb") as fh:
                image_data = fh.read()
            ext = os.path.splitext(str(image_descriptor))[1].lstrip(".")

        ext = ext.lower() or "png"
        digest = hashlib.md5(image_data).hexdigest()[:12]
        name = f"odttpl_{digest}.{ext}"
        self._extra_images[name] = image_data
        return name

    # ------------------------------------------------------------------
    # Manifest helpers
    # ------------------------------------------------------------------

    def _update_manifest(self, manifest_xml: str) -> str:
        """Add manifest entries for all added images."""
        entries = []
        for name in self._extra_images:
            ext = os.path.splitext(name)[1].lstrip(".")
            mime = _mime_for_ext(ext)
            entries.append(
                f"<manifest:file-entry "
                f'manifest:full-path="Pictures/{name}" '
                f'manifest:media-type="{mime}"/>'
            )
        if entries:
            manifest_xml = manifest_xml.replace(
                "</manifest:manifest>",
                "".join(entries) + "</manifest:manifest>",
            )
        return manifest_xml

    # ------------------------------------------------------------------
    # High-level render / save API
    # ------------------------------------------------------------------

    def render(
        self,
        context: Dict[str, Any],
        jinja_env: Optional[Environment] = None,
        autoescape: bool = False,
    ) -> None:
        """Render the template with the given context dict."""
        self._load_template()
        # Reset per-render state
        self._modified_files = {}
        self._extra_images = {}
        self._auto_styles = {}
        self._subdoc_list = []
        self._subdoc_counter = 1

        # Reset any OdtSubdoc objects in the context so they get fresh prefixes
        def _reset_subdocs(v: Any) -> None:
            if isinstance(v, OdtSubdoc):
                v._reset()
            elif isinstance(v, (list, tuple)):
                for item in v:
                    _reset_subdocs(item)
            elif isinstance(v, dict):
                for item in v.values():
                    _reset_subdocs(item)

        for v in context.values():
            _reset_subdocs(v)

        if autoescape:
            if jinja_env is None:
                jinja_env = Environment(autoescape=autoescape)
            else:
                jinja_env.autoescape = autoescape

        # --- content.xml -------------------------------------------------
        content_xml = self.build_content_xml(context, jinja_env)
        if self._auto_styles:
            content_xml = self._inject_auto_styles(content_xml)

        # Merge subdoc automatic styles and images (collected during rendering)
        for subdoc in self._subdoc_list:
            styles_xml_frag = subdoc._get_auto_styles_xml()
            if styles_xml_frag:
                content_xml = content_xml.replace(
                    "</office:automatic-styles>",
                    styles_xml_frag + "</office:automatic-styles>",
                )
            for path, data in subdoc._rendered_images.items():
                fname = path[len("Pictures/"):]
                self._extra_images[fname] = data

        self._modified_files["content.xml"] = content_xml.encode("utf-8")

        # --- styles.xml --------------------------------------------------
        if self._has_zip_entry("styles.xml"):
            try:
                styles_xml = self.build_styles_xml(context, jinja_env)
                self._modified_files["styles.xml"] = styles_xml.encode("utf-8")
            except Exception:
                pass  # styles.xml is optional / may not contain Jinja2 tags

        # --- manifest (images) -------------------------------------------
        if self._extra_images and self._has_zip_entry("META-INF/manifest.xml"):
            manifest_xml = self._read_zip_entry("META-INF/manifest.xml")
            manifest_xml = self._update_manifest(manifest_xml)
            self._modified_files["META-INF/manifest.xml"] = manifest_xml.encode("utf-8")

        self.is_rendered = True

    def save(self, output_file: Union[str, Path, IO[bytes]]) -> None:
        """Write the rendered ODF to *output_file* (path or file-like object)."""
        self._load_template()

        if hasattr(output_file, "write"):
            out: IO[bytes] = output_file  # type: ignore[assignment]
            close_out = False
        else:
            out = open(output_file, "wb")
            close_out = True

        try:
            with zipfile.ZipFile(io.BytesIO(self._template_data), "r") as zin:  # type: ignore[arg-type]
                with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                    existing = {item.filename for item in zin.infolist()}
                    for item in zin.infolist():
                        if item.filename in self._modified_files:
                            zout.writestr(item, self._modified_files[item.filename])
                        else:
                            zout.writestr(item, zin.read(item.filename))
                    # Add new image files
                    for img_name, img_data in self._extra_images.items():
                        path = f"Pictures/{img_name}"
                        if path not in existing:
                            zout.writestr(path, img_data)
        finally:
            if close_out:
                out.close()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_undeclared_variables(
        self, jinja_env: Optional[Environment] = None
    ) -> Set[str]:
        """Return the set of undeclared Jinja2 variables in the template."""
        if jinja_env is None:
            jinja_env = Environment()
        xml = self.get_content_xml()
        xml = self.patch_xml(xml)
        ast = jinja_env.parse(xml)
        return meta.find_undeclared_variables(ast)

    @staticmethod
    def get_file_crc(file_obj: Union[str, Path, IO[bytes]]) -> int:
        if hasattr(file_obj, "read"):
            buf: bytes = file_obj.read()  # type: ignore[union-attr]
        else:
            with open(file_obj, "rb") as fh:
                buf = fh.read()
        return binascii.crc32(buf) & 0xFFFFFFFF
