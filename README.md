# python-odt-template

English | [繁體中文](README.zh-TW.md)

> [!WARNING]
> This project was developed with AI assistance. The code has not been fully reviewed by a human and may contain bugs, security issues, or unexpected behavior. Do not use it in production without your own review and testing.

[![PyPI version](https://img.shields.io/pypi/v/odttpl.svg)](https://pypi.org/project/odttpl/)
[![Python versions](https://img.shields.io/pypi/pyversions/odttpl.svg)](https://pypi.org/project/odttpl/)
[![License: LGPL v2.1](https://img.shields.io/badge/License-LGPL_v2.1-blue.svg)](LICENSE.txt)

Repository: [scbmark/python-odt-template](http://192.168.100.213:3000/scbmark/python-odt-template)

`odttpl` is a Jinja2-powered templating library for ODF documents, primarily used with LibreOffice `.odt` templates. It is inspired by `python-docx-template`, but works with ODF XML and ODT packaging instead of DOCX.

## Features

- Write Jinja2 variables, loops, and conditionals directly in LibreOffice templates
- Repair XML that LibreOffice splits across multiple nodes with `patch_xml()`
- Control full ODF elements with shorthand tags such as `{%tr`, `{%p`, `{%li`, and `{{block ...}}`
- Validate rendered XML and fail early when a Jinja tag crosses an invalid ODF boundary
- Generate inline formatting with `RichText` and full paragraphs with `RichTextParagraph`
- Insert multi-line text safely with `Listing`
- Embed images with `InlineImage`, including manifest updates
- Merge another `.odt` body with `OdtSubdoc`
- Build mixed paragraphs and nested lists programmatically with `StructuredBlock`
- Reuse the same `OdtTemplate` instance across multiple renders

## Installation

```bash
pip install odttpl
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add odttpl
```

Requirements:

- Python 3.8+
- `jinja2`
- `lxml`

## Quick Start

Create a template in LibreOffice Writer:

```text
Hello, {{ name }}!

Your order contains {{ total }} items.
```

Render it from Python:

```python
from odttpl import OdtTemplate

tpl = OdtTemplate("template.odt")
tpl.render({"name": "John", "total": 5})
tpl.save("output.odt")
```

## Template Syntax and ODF Shorthands

Standard Jinja2 syntax works inside the template:

| Syntax | Purpose |
| --- | --- |
| `{{ variable }}` | Output a variable |
| `{% for item in items %} ... {% endfor %}` | Loop |
| `{% if condition %} ... {% endif %}` | Conditional |

LibreOffice often splits one Jinja tag across several XML nodes. `OdtTemplate.patch_xml()` repairs that automatically before rendering.

When a Jinja tag needs to control a whole ODF element, use an element shorthand:

| Shorthand | ODF element | Typical use |
| --- | --- | --- |
| `{%tr` / `{{tr` | `<table:table-row>` | Table row loops |
| `{%tc` / `{{tc` | `<table:table-cell>` | Cell-level control |
| `{%p` / `{{p` | `<text:p>` | Paragraph-level loops or conditionals |
| `{%s` / `{{s` | `<text:span>` | Span-level control |
| `{%li` / `{{li` | `<text:list-item>` | List-item loops |
| `{{block` | `<text:p>` placeholder | Insert mixed block XML from Python |

Examples:

```text
{%p if show_section %}
This paragraph appears only when show_section is true.
{%p endif %}
```

```text
• {%li for item in items %}
• {{ item }}
• {%li endfor %}
```

Use `{{block content}}` when the replacement value needs to emit its own mix of paragraphs and lists instead of text inside the placeholder paragraph.

## RichText and RichTextParagraph

Use `RichText` for inline formatting inside an existing paragraph:

```python
from odttpl import OdtTemplate, RichText

tpl = OdtTemplate("template.odt")

rt = RichText(tpl)
rt.add("Plain text, ")
rt.add("bold", bold=True)
rt.add("red italic", italic=True, color="#CC0000")
rt.add("large text", size=18)

tpl.render({"greeting": rt})
tpl.save("output.odt")
```

Template:

```text
{{ greeting }}
```

`RichText.add()` supports:

- `style` for an existing named character style from the template
- `bold`, `italic`, `underline`, `strike`
- `color`, `size`, `font`
- `superscript`, `subscript`

Use `RichTextParagraph` when Python needs to emit whole paragraphs instead of inline spans:

```python
from odttpl import OdtTemplate, RichText, RichTextParagraph

tpl = OdtTemplate("template.odt")

rp = RichTextParagraph(tpl)
rp.add(RichText(tpl, "Heading", bold=True), parastyle="Heading_20_1")
rp.add(RichText(tpl, "Body paragraph"))

tpl.render({"content": rp})
tpl.save("output.odt")
```

Template:

```text
{{p content }}
```

Aliases:

- `R` = `RichText`
- `RP` = `RichTextParagraph`

## Listing

`Listing` turns plain text with control characters into ODF-safe XML:

```python
from odttpl import OdtTemplate, Listing

tpl = OdtTemplate("template.odt")
tpl.render({"body": Listing("Line one\nLine two\nIndented\tvalue")})
tpl.save("output.odt")
```

Control characters:

| Character | Result |
| --- | --- |
| `\n` | `<text:line-break/>` |
| `\t` | `<text:tab/>` |
| `\a` | Start a new paragraph |
| `\f` | Insert a soft page break and start a new paragraph |

## InlineImage

Use `InlineImage` to embed a picture into `Pictures/` and reference it from the rendered XML:

```python
from odttpl import OdtTemplate, InlineImage

tpl = OdtTemplate("template.odt")
tpl.render({"logo": InlineImage(tpl, "logo.png", width="4cm")})
tpl.save("output.odt")
```

Template:

```text
{{ logo }}
```

Notes:

- `width` and `height` accept ODF length strings such as `"4cm"` or `"2in"`
- If only one dimension is given, the other is computed to preserve aspect ratio when image metadata is available
- `anchor` defaults to `"as-char"` and can be changed to values such as `"paragraph"` or `"page"`

## OdtSubdoc

Use `new_subdoc()` to insert the body of another `.odt` file:

```python
from odttpl import OdtTemplate

tpl = OdtTemplate("master.odt")
chapter = tpl.new_subdoc("chapter.odt")
tpl.render({"chapter": chapter})
tpl.save("output.odt")
```

Template:

```text
{{p chapter }}
```

What happens automatically:

- Auto styles from the sub-document are renamed with an `odttpl_sd...` prefix and merged into the master document
- Images from the sub-document are copied into the output archive
- Each render resets sub-document state so repeated renders stay stable

Current limitation:

- Named paragraph and character styles that exist only in the sub-document are not fully merged into the master document; when missing, LibreOffice falls back to master defaults

## StructuredBlock

`StructuredBlock` is a Python-side builder for output that mixes free paragraphs, nested numbered lists, bullet lists, and continuation paragraphs inside list items.

Template:

```text
{{block content}}
```

Python:

```python
from odttpl import OdtTemplate, StructuredBlock

tpl = OdtTemplate("report.odt")
block = StructuredBlock(tpl)

block.add_paragraph("Findings:")
block.add_list_item("Authentication", level=1)
block.add_list_item("Password reset flow", level=2)
block.add_paragraph("Affects SSO and local accounts.", in_list_item=True)
block.add_paragraph("Standalone note between list segments.", margin_left="1cm")
block.add_list_item("Session pinning", level=2)  # resumes numbering by default
block.add_list_item("Restart this nested sequence", level=2, continue_numbering=False)
block.close_list()
block.add_paragraph("Summary after the list.")

tpl.render({"content": block})
tpl.save("output.odt")
```

Behavior summary:

- `add_paragraph(..., in_list_item=True)` appends another paragraph inside the current `<text:list-item>`
- `add_paragraph(..., in_list_item=False)` creates a standalone sibling paragraph
- If a standalone paragraph splits a list, the next compatible `add_list_item()` resumes numbering by default
- `continue_numbering=False` starts a new list segment instead of resuming
- `continue_numbering=True` is only valid when a compatible suspended list context exists
- `close_list()` clears both the live list context and any resumable suspended context

### Custom list styles

Use `NumberedListStyle` for programmatic numbered lists:

```python
from odttpl import NumberedListStyle, LevelSpec, LabelFollowedBy, StructuredBlock

numbering = NumberedListStyle(
    tpl,
    levels=[
        LevelSpec(format="A", suffix=")"),
        LevelSpec(format="1", suffix=".", display_levels=2),
        LevelSpec(format="1", label_followed_by=LabelFollowedBy.SPACE),
    ],
)

block = StructuredBlock(tpl, default_list_style=numbering)
```

Use `BulletListStyle` for bullet lists:

```python
from odttpl import BulletListStyle, BulletLevelSpec, StructuredBlock

bullets = BulletListStyle(
    tpl,
    levels=[
        BulletLevelSpec(bullet_char="•", space_before="0.8cm"),
        {"bullet_char": "◦", "space_before": "1.4cm"},
    ],
)

block = StructuredBlock(tpl, default_list_style=bullets)
```

You can also reuse a named list style that already exists in the template:

```python
block = StructuredBlock(tpl, default_list_style="WWNum1")
```

Passing a string uses that style name verbatim. `odttpl` does not auto-register or redefine it.

Paragraph styling inside a block:

- `parastyle="Heading_20_1"` uses an existing paragraph style from the template
- `margin_left=` and `text_indent=` create an automatic paragraph style unless `parastyle` is already set
- `RichText` values can be used in both `add_paragraph()` and `add_list_item()`

Aliases:

- `SB` = `StructuredBlock`
- `NLS` = `NumberedListStyle`

## Advanced Usage

Autoescape:

```python
tpl.render(context, autoescape=True)
```

Custom Jinja environment:

```python
from jinja2 import Environment

env = Environment()
env.filters["currency"] = lambda v: f"${v:,.2f}"

tpl.render(context, jinja_env=env)
```

Inspect undeclared variables:

```python
variables = tpl.get_undeclared_variables()
```

Multiple renders with one template object:

```python
tpl = OdtTemplate("template.odt")

for record in records:
    tpl.render(record)
    tpl.save(f"output_{record['id']}.odt")
```

Each `render()` starts from the original template bytes and resets per-render registries for styles, images, and sub-documents.

## API Overview

| API | Purpose |
| --- | --- |
| `OdtTemplate(template_file)` | Load a template from a path, `Path`, or file-like object |
| `OdtTemplate.render(context, jinja_env=None, autoescape=False)` | Render `content.xml` and optional `styles.xml` |
| `OdtTemplate.save(output_file)` | Save the rendered document to a path or file-like object |
| `OdtTemplate.get_undeclared_variables()` | Inspect the template for undeclared Jinja variables |
| `OdtTemplate.new_subdoc(path=None)` | Create an `OdtSubdoc` tied to the template |
| `RichText`, `R` | Build inline formatted text |
| `RichTextParagraph`, `RP` | Build one or more full paragraphs |
| `Listing` | Convert plain text control characters into ODF-safe XML |
| `InlineImage` | Embed images in the output package |
| `OdtSubdoc` | Represent a sub-document merged at render time |
| `StructuredBlock`, `SB` | Build mixed paragraph and list output |
| `NumberedListStyle`, `NLS` | Define numbered list styles in Python |
| `BulletListStyle` | Define bullet list styles in Python |
| `LevelSpec`, `BulletLevelSpec`, `LabelFollowedBy` | Configure list style levels |
| `StructuredBlockError` | Raised for invalid block-building sequences |

## Development

```bash
git clone http://192.168.100.213:3000/scbmark/python-odt-template.git
cd python-odt-template
uv venv
uv pip install -e ".[dev]"
uv run pytest tests/ -v
```

The current documentation in this repository is aligned with the existing automated test suite, including `tests/test_template.py` and `tests/test_structured_block.py`.

## License

This project is licensed under the [GNU Lesser General Public License v2.1](LICENSE.txt).
