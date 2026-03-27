# python-odt-template

English | [繁體中文](README.zh-TW.md)

> [!WARNING]
> This project was developed with AI assistance (Vibe Coding). The code has not been fully reviewed by a human and may contain bugs, security vulnerabilities, or unexpected behavior. **Do not use in production environments. Use at your own risk.** Issues and PRs to improve the project are welcome.

[![PyPI version](https://img.shields.io/pypi/v/odttpl.svg)](https://pypi.org/project/odttpl/)
[![Python versions](https://img.shields.io/pypi/pyversions/odttpl.svg)](https://pypi.org/project/odttpl/)
[![License: LGPL v2.1](https://img.shields.io/badge/License-LGPL_v2.1-blue.svg)](LICENSE.txt)
[![Tests](https://github.com/yourname/python-odt-template/actions/workflows/test.yml/badge.svg)](https://github.com/yourname/python-odt-template/actions)

A [Jinja2](https://jinja.palletsprojects.com/)-powered templating library that uses LibreOffice `.odt` files as templates to render documents. Inspired by and modeled after [python-docx-template](https://github.com/elapouya/python-docx-template), but re-implemented for the ODF format.

---

## Features

- **Full Jinja2 support**: Use variables, loops, and conditionals directly inside `.odt` templates
- **Automatic XML repair**: LibreOffice may split tags across XML nodes when saving; `patch_xml()` restores them automatically
- **Table row / paragraph level control**: Shorthand prefixes like `{%tr` and `{%p` let you control entire ODF elements
- **RichText**: Mix bold, italic, color, font size, and other formats within a single variable
- **Listing**: Full support for multi-line text including line breaks, tabs, and page breaks
- **InlineImage**: Embed images and automatically update the ODF manifest
- **Subdoc**: Embed the body of another `.odt` file (sub-document) into the master template, with automatic style and image merging
- **Multiple renders**: A single `OdtTemplate` object can be rendered repeatedly with different data

---

## Installation

```bash
pip install odttpl
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add odttpl
```

**Requirements**: Python 3.8+. Dependencies `jinja2` and `lxml` are installed automatically.

---

## Quick Start

**1. Prepare a template `template.odt`**

Type the following in LibreOffice Writer and save:

```
Hello, {{ name }}!

Your order contains {{ total }} items.
```

**2. Render and save**

```python
from odttpl import OdtTemplate

tpl = OdtTemplate("template.odt")
tpl.render({"name": "John", "total": 5})
tpl.save("output.odt")
```

**3. Open `output.odt` in LibreOffice** to see the rendered result.

---

## Creating ODF Templates

Type Jinja2 tags directly in LibreOffice Writer:

| Syntax | Purpose |
|--------|---------|
| `{{ variable }}` | Output a variable |
| `{% for item in items %}` … `{% endfor %}` | Loop |
| `{% if condition %}` … `{% endif %}` | Conditional |

> **Note**: LibreOffice may split `{{ variable }}` across multiple XML nodes when saving.
> `OdtTemplate` automatically calls `patch_xml()` on load to fix this — no manual action needed.

---

## Jinja2 Tag Shorthand Prefixes

ODF XML has a strict nesting structure. To control an entire **table row** or **paragraph** with Jinja2, use tags with the appropriate prefix inside the corresponding XML element. `patch_xml` will then replace the entire element with a plain Jinja2 tag.

| Prefix | ODF Element | Typical Use |
|--------|-------------|-------------|
| `{%tr` / `{{tr` | `<table:table-row>` | Table row loops |
| `{%tc` / `{{tc` | `<table:table-cell>` | Cell-level control |
| `{%p` / `{{p` | `<text:p>` | Paragraph-level conditionals / loops |
| `{%s` / `{{s` | `<text:span>` | Span-level control |

### Table Row Loop (`{%tr`)

Create a two-column table in LibreOffice:

| Column A | Column B |
|----------|----------|
| `{%tr for item in rows %}` | (empty) |
| `{{ item.name }}` | `{{ item.price }}` |
| `{%tr endfor %}` | (empty) |

Rows containing `{%tr` are removed after rendering; only the data rows are repeated.

### Paragraph-Level Conditional (`{%p`)

```
{%p if show_section %}
This entire paragraph only appears when show_section is True.
{%p endif %}
```

Paragraphs containing `{%p` are removed after rendering.

---

## RichText Formatted Text

Use `RichText` (alias `R`) to mix multiple formats within a single variable:

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

In the template, write: `{{ greeting }}`

### `RichText.add()` Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | str | Text content |
| `style` | str | A named character style already defined in the template |
| `bold` | bool | Bold |
| `italic` | bool | Italic |
| `underline` | bool / str | Underline; optionally specify style such as `"dotted"`, `"solid"` |
| `strike` | bool | Strikethrough |
| `color` | str | Text color in hex, e.g. `"#FF0000"` |
| `size` | int / float | Font size in points |
| `font` | str | Font name, e.g. `"Noto Sans"` |
| `superscript` | bool | Superscript |
| `subscript` | bool | Subscript |

### RichTextParagraph — Multi-paragraph Formatting

To output entire paragraphs with paragraph styles from Python, use `RichTextParagraph` (alias `RP`) and replace the placeholder paragraph in the template with `{{p content }}`:

```python
from odttpl import OdtTemplate, RichText, RichTextParagraph

tpl = OdtTemplate("template.odt")

rp = RichTextParagraph(tpl)
rp.add(RichText(tpl, "Heading text", bold=True), parastyle="Heading_20_1")
rp.add(RichText(tpl, "Body paragraph"))

tpl.render({"content": rp})
tpl.save("output.odt")
```

---

## Listing — Multi-line Text

Use `Listing` when a string contains newlines or tabs and you don't want to build the XML manually:

```python
from odttpl import OdtTemplate, Listing

tpl = OdtTemplate("template.odt")
tpl.render({"body": Listing("Line one\nLine two\nLine three")})
tpl.save("output.odt")
```

| Special Character | Rendered As |
|-------------------|-------------|
| `\n` | In-paragraph line break (`<text:line-break/>`) |
| `\t` | Tab stop (`<text:tab/>`) |
| `\a` | New paragraph (same paragraph style) |
| `\f` | Soft page break followed by a new paragraph |

---

## InlineImage — Embed Images

```python
from odttpl import OdtTemplate, InlineImage

tpl = OdtTemplate("template.odt")
tpl.render({"logo": InlineImage(tpl, "logo.png", width="4cm", height="2cm")})
tpl.save("output.odt")
```

In the template, write: `{{ logo }}` (inside a paragraph)

`InlineImage` automatically:
1. Embeds the image into the `Pictures/` directory inside the ODF ZIP
2. Updates `META-INF/manifest.xml`
3. Generates the corresponding `<draw:frame>` XML

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `tpl` | OdtTemplate | Parent template object |
| `image_descriptor` | str / Path / file-like | Image path or BytesIO object |
| `width` | str | Width, e.g. `"5cm"`, `"2in"` |
| `height` | str | Height, e.g. `"3cm"` |
| `anchor` | str | Anchor type; default `"as-char"` (inline); `"paragraph"` for paragraph anchor |

---

## Subdoc — Embed Another ODT File

Use `new_subdoc()` to embed the body of another `.odt` file into the master template. Paragraph styles and embedded images from the sub-document are automatically merged into the output.

```python
from odttpl import OdtTemplate

tpl = OdtTemplate("main.odt")
sub = tpl.new_subdoc("chapter.odt")
tpl.render({"chapter": sub})
tpl.save("output.odt")
```

In the master template, place `{{p chapter }}` on its own paragraph where you want the sub-document content inserted. The `{{p` prefix is required so the entire placeholder paragraph is replaced.

### Embedding multiple sub-documents

```python
tpl = OdtTemplate("main.odt")
intro = tpl.new_subdoc("intro.odt")
body  = tpl.new_subdoc("body.odt")
tpl.render({"intro": intro, "body": body})
tpl.save("output.odt")
```

### Notes

- **Style merging**: automatic styles (paragraph, character, etc.) defined in the sub-document are renamed with a unique prefix before being injected into the master to avoid collisions.
- **Image merging**: images embedded in the sub-document are copied into the output archive automatically.
- **Template variables**: sub-documents are plain `.odt` files — Jinja2 tags inside them are **not** evaluated. Only the rendered body XML is inserted.

---

## Advanced Usage

### Autoescape

If data comes from user input, enable `autoescape` to prevent XML injection:

```python
tpl.render(context, autoescape=True)
```

### Custom Jinja2 Environment

Pass a custom `jinja2.Environment` to add filters or extensions:

```python
from jinja2 import Environment

env = Environment()
env.filters["currency"] = lambda v: f"${v:,.2f}"

tpl.render(context, jinja_env=env)
```

### Inspect Undeclared Variables

```python
variables = tpl.get_undeclared_variables()
print(variables)  # {'name', 'total', 'items', ...}
```

### Multiple Renders

```python
tpl = OdtTemplate("template.odt")

for record in records:
    tpl.render(record)
    tpl.save(f"output_{record['id']}.odt")
```

Each call to `render()` starts fresh from the original template and does not carry over state from previous renders.

---

## Development

```bash
git clone https://github.com/yourname/python-odt-template.git
cd python-odt-template

# Create a virtual environment and install dev dependencies
uv venv && uv pip install -e ".[dev]"

# Run tests
uv run pytest tests/ -v
```

Issues and Pull Requests are welcome!

---

## License

This project is licensed under the [GNU Lesser General Public License v2.1](LICENSE.txt), the same license as [python-docx-template](https://github.com/elapouya/python-docx-template).
