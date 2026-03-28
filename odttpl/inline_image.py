# -*- coding: utf-8 -*-
"""
InlineImage – embed a picture inline inside an ODF paragraph.

In ODF, images are stored in the ``Pictures/`` directory inside the ZIP
archive and referenced from ``content.xml`` via a ``<draw:frame>`` /
``<draw:image>`` element.  ``OdtTemplate._add_image`` handles storing the
bytes; ``InlineImage.__str__`` returns the XML fragment that Jinja2 inserts
into the rendered document.

Usage::

    from odttpl import OdtTemplate, InlineImage

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

    If only one of ``width`` / ``height`` is given, the other is computed
    automatically to preserve the image's aspect ratio.  If both are given,
    they are used as-is (forced / non-proportional scaling).
"""

from __future__ import annotations

import os
import re
import struct
from typing import IO, Optional, Tuple, Union, cast
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers – image size detection (no external dependencies)
# ---------------------------------------------------------------------------

def _get_image_size(data: bytes) -> Optional[Tuple[int, int]]:
    """Return ``(width_px, height_px)`` from raw image bytes.

    Supports PNG, JPEG, GIF87a/89a, and BMP.
    Returns ``None`` when the format is not recognised or data is too short.
    """
    if len(data) < 24:
        return None

    # PNG: signature 8 bytes, then IHDR chunk: 4 len + 4 "IHDR" + 4 w + 4 h
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack('>II', data[16:24])
        return (w, h)

    # GIF87a / GIF89a: 6-byte header, then 2-byte LE width, 2-byte LE height
    if data[:6] in (b'GIF87a', b'GIF89a'):
        w, h = struct.unpack('<HH', data[6:10])
        return (w, h)

    # BMP: 2-byte magic "BM", then 4-byte file size, 4 reserved, 4 offset,
    #      then BITMAPINFOHEADER starting at byte 14: 4 size, 4 w, 4 h (signed)
    if data[:2] == b'BM' and len(data) >= 26:
        w, h = struct.unpack('<ii', data[18:26])
        return (abs(w), abs(h))

    # JPEG: scan for SOF0/SOF1/SOF2 markers (FF C0 / FF C1 / FF C2)
    if data[:2] == b'\xff\xd8':
        i = 2
        while i + 3 < len(data):
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                if i + 9 <= len(data):
                    h, w = struct.unpack('>HH', data[i + 5: i + 9])
                    return (w, h)
            # advance past this segment
            if i + 4 > len(data):
                break
            seg_len = struct.unpack('>H', data[i + 2: i + 4])[0]
            i += 2 + seg_len
        return None

    return None


# ---------------------------------------------------------------------------
# Helpers – ODF length string parsing / formatting
# ---------------------------------------------------------------------------

_LENGTH_RE = re.compile(
    r'^\s*([0-9]*\.?[0-9]+)\s*(cm|mm|in|pt|px|em|pc)\s*$',
    re.IGNORECASE,
)


def _parse_length(s: str) -> Tuple[float, str]:
    """Parse an ODF length string such as ``"4cm"`` into ``(4.0, "cm")``."""
    m = _LENGTH_RE.match(s)
    if not m:
        raise ValueError(f"Cannot parse ODF length string: {s!r}")
    return float(m.group(1)), m.group(2).lower()


def _format_length(value: float, unit: str) -> str:
    """Format a numeric value + unit back to an ODF length string."""
    # Keep at most 4 decimal places, strip trailing zeros
    return f"{value:.4f}".rstrip('0').rstrip('.') + unit


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
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_image_bytes(self) -> bytes:
        """Read raw bytes from *image_descriptor* without side-effects.

        For file-like objects the stream position is restored to its original
        location so that subsequent reads (e.g. ``_add_image``) still work.
        """
        desc = self.image_descriptor
        if hasattr(desc, 'read'):
            io_desc = cast(IO[bytes], desc)
            pos = io_desc.tell() if hasattr(desc, 'tell') else None
            data: bytes = io_desc.read()
            if pos is not None and hasattr(desc, 'seek'):
                io_desc.seek(pos)
            return data
        else:
            with open(desc, 'rb') as fh:
                return fh.read()

    def _resolve_size(self) -> Tuple[Optional[str], Optional[str]]:
        """Return ``(width_str, height_str)`` after applying proportional scaling.

        - Both given  → use as-is (forced scaling).
        - Only width  → compute height proportionally.
        - Only height → compute width proportionally.
        - Neither     → ``(None, None)``.
        """
        width, height = self.width, self.height

        # Both specified – honour the user's explicit values unchanged.
        if width and height:
            return width, height

        # Neither specified – no size attributes needed.
        if not width and not height:
            return None, None

        # One dimension specified – compute the other from the aspect ratio.
        data = self._read_image_bytes()
        size = _get_image_size(data)
        if size is None:
            # Cannot determine image dimensions; return what we have.
            return width, height

        img_w_px, img_h_px = size
        if img_w_px == 0 or img_h_px == 0:
            return width, height

        aspect = img_w_px / img_h_px  # width / height

        if width and not height:
            val, unit = _parse_length(width)
            computed_height = val / aspect
            return width, _format_length(computed_height, unit)

        # height and not width
        assert height is not None
        val, unit = _parse_length(height)
        computed_width = val * aspect
        return _format_length(computed_width, unit), height

    # ------------------------------------------------------------------
    # XML generation
    # ------------------------------------------------------------------

    def _build_xml(self) -> str:
        image_name = self.tpl._add_image(self.image_descriptor)

        resolved_width, resolved_height = self._resolve_size()

        # Build size attributes
        size_attrs = ""
        if resolved_width:
            size_attrs += f' svg:width="{resolved_width}"'
        if resolved_height:
            size_attrs += f' svg:height="{resolved_height}"'

        # Unique frame name based on the image filename
        frame_name = os.path.splitext(image_name)[0]

        xml = (
            f'<draw:frame draw:name="{frame_name}" '
            f'text:anchor-type="{self.anchor}"'
            f"{size_attrs} "
            f'draw:z-index="0">'
            f"<draw:image "
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
