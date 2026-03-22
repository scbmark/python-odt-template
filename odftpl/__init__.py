# -*- coding: utf-8 -*-
"""
odftpl – ODF template engine for Python.

Mirrors the API of python-docx-template (docxtpl) but targets
OpenDocument Format (.odt, .ods, .odp) files produced by
LibreOffice / OpenOffice.
"""

__version__ = "0.1.0"

# flake8: noqa
from .template import OdfTemplate
from .richtext import RichText, RichTextParagraph, R, RP
from .listing import Listing
from .inline_image import InlineImage
