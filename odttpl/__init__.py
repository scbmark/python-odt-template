# -*- coding: utf-8 -*-
"""
odttpl – ODT template engine for Python.

Mirrors the API of python-docx-template (docxtpl) but targets
OpenDocument Format (.odt, .ods, .odp) files produced by
LibreOffice / OpenOffice.
"""

__version__ = "0.1.0"


from .template import OdtTemplate  # noqa: F401
from .richtext import RichText, RichTextParagraph, R, RP  # noqa: F401
from .listing import Listing  # noqa: F401
from .inline_image import InlineImage  # noqa: F401
from .subdoc import OdtSubdoc  # noqa: F401
from .structured_block import (  # noqa: F401
    StructuredBlock,
    NumberedListStyle,
    BulletListStyle,
    LevelSpec,
    BulletLevelSpec,
    StructuredBlockError,
    SB,
    NLS,
)
