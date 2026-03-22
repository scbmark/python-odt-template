"""
Helper script to generate minimal .odt test-template files programmatically.

Run once::

    python tests/make_templates.py

The resulting .odt files in tests/templates/ can then be used by the test
suite without needing a LibreOffice installation.
"""
import io
import zipfile
import os

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Minimal ODF skeleton
# ---------------------------------------------------------------------------

MIMETYPE = b"application/vnd.oasis.opendocument.text"

MANIFEST_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest
    xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
    manifest:version="1.2">
  <manifest:file-entry manifest:full-path="/"
      manifest:version="1.2"
      manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml"
      manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml"
      manifest:media-type="text/xml"/>
</manifest:manifest>
"""

STYLES_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
    office:version="1.2">
  <office:styles/>
  <office:automatic-styles/>
  <office:master-styles/>
</office:document-styles>
"""

CONTENT_XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
    xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
    office:version="1.2">
  <office:automatic-styles/>
  <office:body>
    <office:text>
{body}
    </office:text>
  </office:body>
</office:document-content>
"""


def make_odt(filename: str, body: str) -> None:
    """Write a minimal .odt file with the given *body* XML snippet."""
    path = os.path.join(TEMPLATES_DIR, filename)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be the first entry and stored (not deflated)
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, MIMETYPE)
        zf.writestr("META-INF/manifest.xml", MANIFEST_XML.encode("utf-8"))
        zf.writestr("styles.xml", STYLES_XML.encode("utf-8"))
        content = CONTENT_XML_TEMPLATE.format(body=body)
        zf.writestr("content.xml", content.encode("utf-8"))
    with open(path, "wb") as fh:
        fh.write(buf.getvalue())
    print(f"Created {path}")


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

make_odt(
    "simple_var.odt",
    '<text:p text:style-name="Default">Hello {{ name }}!</text:p>',
)

make_odt(
    "loop_table.odt",
    """\
      <table:table table:name="T1">
        <table:table-column/>
        <table:table-column/>
        <table:table-row>
          <table:table-cell><text:p>{%tr for item in items %}</text:p></table:table-cell>
        </table:table-row>
        <table:table-row>
          <table:table-cell><text:p>{{ item.name }}</text:p></table:table-cell>
          <table:table-cell><text:p>{{ item.value }}</text:p></table:table-cell>
        </table:table-row>
        <table:table-row>
          <table:table-cell><text:p>{%tr endfor %}</text:p></table:table-cell>
        </table:table-row>
      </table:table>""",
)

make_odt(
    "listing.odt",
    '<text:p text:style-name="Default">{{ body }}</text:p>',
)

make_odt(
    "conditional.odt",
    """\
      <text:p>{%p if show %}</text:p>
      <text:p text:style-name="Default">Visible</text:p>
      <text:p>{%p endif %}</text:p>""",
)

print("All templates created.")
