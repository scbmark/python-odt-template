# -*- coding: utf-8 -*-
"""
InlineImage – embed a picture inline inside an ODF paragraph.

In ODF, images are stored in the ``Pictures/`` directory inside the ZIP
archive and referenced from ``content.xml`` via a ``<draw:frame>`` /
``<draw:image>`` element.  ``OdtTemplate._add_image`` handles storing the
bytes; ``InlineImage.__str__`` returns the XML fragment that Jinja2 inserts
into the rendered document.

Usage::

    from odttlp import OdtTemplate, InlineImage

    tpl = OdtTemplate("template.odt")
    context = {
        "logo": InlineImage(tpl, "logo.png", width="4cm", height="2cm"),
    }
    tpl.render(context)
    tpl.save("output.odt")

In the .odt template put ``{{ logo }}`` inside a paragraph.

.. note::
    The ``width`` / ``height`` arguments accept any ODF-compatible length
    string: ``"4cm"``, ``"2in"``, ``"96pt"``, etc.  If both are omitted the
    image is inserted without explicit size (the viewer will use the image's
    natural size).
"""
from __future__ import annotations

import os
from typing import IO, Optional, Union
from pathlib import Path


class InlineImage:
    """Inline image for ODF templates.

    Parameters
    ----------
    tpl:
        The parent ``OdtTemplate`` instance.
    image_descriptor:
        Path to the image file *or* a file-like object (``io.BytesIO``, …).
    width:
        ODF length string for the frame width, e.g. ``"5cm"``.
    height:
        ODF length string for the frame height, e.g. ``"3cm"``.
    anchor:
        ``text:anchor-type`` value.  Defaults to ``"as-char"`` (inline).
        Other useful values: ``"paragraph"``, ``"page"``.
    """

    def __init__(
        self,
        tpl,
        image_descriptor: Union[str, Path, IO[bytes]],
        width: Optional[str] = None,
        height: Optional[str] = None,
        anchor: str = "as-char",
    ) -> None:
        self.tpl = tpl
        self.image_descriptor = image_descriptor
        self.width = width
        self.height = height
        self.anchor = anchor

    # ------------------------------------------------------------------
    # XML generation
    # ------------------------------------------------------------------

    def _build_xml(self) -> str:
        image_name = self.tpl._add_image(self.image_descriptor)

        # Build size attributes
        size_attrs = ""
        if self.width:
            size_attrs += f' svg:width="{self.width}"'
        if self.height:
            size_attrs += f' svg:height="{self.height}"'

        # Unique frame name based on the image filename
        frame_name = os.path.splitext(image_name)[0]

        xml = (
            f'<draw:frame draw:name="{frame_name}" '
            f'text:anchor-type="{self.anchor}"'
            f"{size_attrs} "
            f'draw:z-index="0">'
            f'<draw:image '
            f'xlink:href="Pictures/{image_name}" '
            f'xlink:type="simple" '
            f'xlink:show="embed" '
            f'xlink:actuate="onLoad"/>'
            f"</draw:frame>"
        )
        return xml

    # ------------------------------------------------------------------
    # String protocol – called by Jinja2 during rendering
    # ------------------------------------------------------------------

    def __unicode__(self) -> str:
        return self._build_xml()

    def __str__(self) -> str:
        return self._build_xml()

    def __html__(self) -> str:
        return self._build_xml()
