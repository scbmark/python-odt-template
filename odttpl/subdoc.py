# -*- coding: utf-8 -*-
"""
Subdocument support for OdtTemplate.

Allows embedding an existing .odt file into a master OdtTemplate.

Usage::

    tpl = OdtTemplate("master.odt")
    sd = tpl.new_subdoc("chapter1.odt")
    tpl.render({"chapter": sd})

In the master template, use ``{%p chapter %}`` to insert the sub-document's
paragraphs at block level (the surrounding ``<text:p>`` is stripped and
replaced by the sub-document's body content).  You can also use
``{{ chapter }}`` inline, though block-level insertion is more common.
"""

from __future__ import annotations

import copy
import re
import zipfile
from typing import Dict, List, Optional, TYPE_CHECKING

from lxml import etree

if TYPE_CHECKING:
    from .template import OdtTemplate

_OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
_STYLE_NS = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"


class OdtSubdoc:
    """Wraps an .odt file so it can be embedded into an ``OdtTemplate``.

    Create instances via ``OdtTemplate.new_subdoc()``::

        sd = tpl.new_subdoc("chapter.odt")
        tpl.render({"chapter": sd})

    Template usage (block-level insertion)::

        {%p chapter %}

    The ``{%p … %}`` shorthand removes the enclosing ``<text:p>`` and replaces
    it with the sub-document's paragraphs and tables.

    **Automatic styles** from the sub-document are renamed with a unique prefix
    and injected into the master document so there are no name collisions.
    **Images** inside the sub-document are also copied into the output archive.

    Named paragraph/character styles that exist in the sub-document but not in
    the master document will fall back to the master document's defaults; full
    named-style merging is not yet implemented.
    """

    def __init__(self, tpl: "OdtTemplate", odt_path: Optional[str] = None) -> None:
        self.tpl = tpl
        # Original state – loaded from file, never mutated:
        self._orig_body_xml: str = ""
        self._orig_auto_style_elements: List[etree._Element] = []
        self._orig_images: Dict[str, bytes] = {}  # "Pictures/foo.png" -> bytes
        # Per-render state – reset at the start of each render:
        self._prefix: Optional[str] = None
        self._rendered_body_xml: str = ""
        self._rendered_auto_style_elements: List[etree._Element] = []
        self._rendered_images: Dict[str, bytes] = {}  # renamed "Pictures/…" -> bytes

        if odt_path is not None:
            self._load(odt_path)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self, path: str) -> None:
        with zipfile.ZipFile(path, "r") as zf:
            # --- content.xml ---
            root = etree.fromstring(zf.read("content.xml"))

            auto_styles_el = root.find(f"{{{_OFFICE_NS}}}automatic-styles")
            if auto_styles_el is not None:
                self._orig_auto_style_elements = list(auto_styles_el)

            body_el = root.find(f".//{{{_OFFICE_NS}}}text")
            if body_el is not None:
                self._orig_body_xml = "".join(
                    etree.tostring(child, encoding="unicode") for child in body_el
                )

            # --- Images ---
            for name in zf.namelist():
                if name.startswith("Pictures/"):
                    self._orig_images[name] = zf.read(name)

    # ------------------------------------------------------------------
    # Per-render lifecycle
    # ------------------------------------------------------------------

    def _reset(self) -> None:
        """Reset per-render state.  Called by ``OdtTemplate.render()``."""
        self._prefix = None
        self._rendered_body_xml = ""
        self._rendered_auto_style_elements = []
        self._rendered_images = {}

    def _ensure_renamed(self) -> None:
        """Assign a render-unique prefix and rename all auto-style / image
        references.  Idempotent within one render cycle."""
        if self._prefix is not None:
            return

        idx = self.tpl._subdoc_counter
        self.tpl._subdoc_counter += 1
        self._prefix = f"odttpl_sd{idx}_"

        # Collect automatic-style names defined in this sub-document
        auto_names: set = set()
        for el in self._orig_auto_style_elements:
            name = el.get(f"{{{_STYLE_NS}}}name")
            if name:
                auto_names.add(name)

        body_xml = self._orig_body_xml

        # Rename style-name attribute values that refer to auto styles
        if auto_names:
            prefix = self._prefix

            def _repl_style(m: re.Match) -> str:
                attr, val = m.group(1), m.group(2)
                if val in auto_names:
                    return f'{attr}="{prefix}{val}"'
                return m.group(0)

            body_xml = re.sub(
                r'([\w:.-]*style-name)="([^"]*)"',
                _repl_style,
                body_xml,
            )

        # Rename image paths and update xlink:href references
        rendered_images: Dict[str, bytes] = {}
        for orig_path, data in self._orig_images.items():
            fname = orig_path[len("Pictures/"):]
            new_path = f"Pictures/odttpl_sd{idx}_{fname}"
            rendered_images[new_path] = data
            body_xml = body_xml.replace(f'"{orig_path}"', f'"{new_path}"')
        self._rendered_images = rendered_images
        self._rendered_body_xml = body_xml

        # Clone auto-style elements and rename style:name attributes
        new_elements: List[etree._Element] = []
        for el in self._orig_auto_style_elements:
            el_copy = copy.deepcopy(el)
            name = el_copy.get(f"{{{_STYLE_NS}}}name")
            if name and name in auto_names:
                el_copy.set(f"{{{_STYLE_NS}}}name", self._prefix + name)
            # Rename any inner attribute that references another auto style
            for attr, val in list(el_copy.attrib.items()):
                local = attr.split("}")[-1]
                if local != "name" and "style-name" in local and val in auto_names:
                    el_copy.set(attr, self._prefix + val)
            new_elements.append(el_copy)
        self._rendered_auto_style_elements = new_elements

    # ------------------------------------------------------------------
    # Helpers used by OdtTemplate after rendering
    # ------------------------------------------------------------------

    def _get_auto_styles_xml(self) -> str:
        return "".join(
            etree.tostring(el, encoding="unicode")
            for el in self._rendered_auto_style_elements
        )

    # ------------------------------------------------------------------
    # Jinja2 rendering protocol
    # ------------------------------------------------------------------

    def _get_xml(self) -> str:
        self._ensure_renamed()
        self.tpl._register_subdoc(self)
        return self._rendered_body_xml

    def __str__(self) -> str:
        return self._get_xml()

    def __html__(self) -> str:
        return self._get_xml()
