# python-odt-template

[English](README.md) | 繁體中文

> [!WARNING]
> 這個專案是在 AI 輔助下開發的。程式碼尚未經過完整的人工作業審查，可能仍有錯誤、安全性問題或非預期行為。若要使用於正式環境，請先自行審查並完成測試。

[![PyPI version](https://img.shields.io/pypi/v/odttpl.svg)](https://pypi.org/project/odttpl/)
[![Python versions](https://img.shields.io/pypi/pyversions/odttpl.svg)](https://pypi.org/project/odttpl/)
[![License: LGPL v2.1](https://img.shields.io/badge/License-LGPL_v2.1-blue.svg)](LICENSE.txt)

儲存庫：[scbmark/python-odt-template](http://192.168.100.213:3000/scbmark/python-odt-template)

`odttpl` 是一個以 Jinja2 為核心的 ODF 文件樣板函式庫，主要用在 LibreOffice `.odt` 範本。它的使用方式參考 `python-docx-template`，但底層處理的是 ODF XML 與 ODT 封裝格式，而不是 DOCX。

## 特色

- 直接在 LibreOffice 範本中撰寫 Jinja2 變數、迴圈與條件式
- 透過 `patch_xml()` 修補 LibreOffice 把同一個 Jinja 標籤切碎成多個 XML 節點的情況
- 使用 `{%tr`、`{%p`、`{%li`、`{{block ...}}` 等 shorthand 控制整個 ODF 元素
- 在渲染後驗證 XML 是否仍為 well-formed，提早發現跨元素邊界的 Jinja 錯誤
- 以 `RichText` 產生行內格式化文字，或用 `RichTextParagraph` 產生完整段落
- 以 `Listing` 安全插入多行文字
- 以 `InlineImage` 嵌入圖片並自動更新 manifest
- 以 `OdtSubdoc` 合併另一個 `.odt` 文件本文
- 以 `StructuredBlock` 在 Python 中組出段落、巢狀編號清單與項目內續段
- 同一個 `OdtTemplate` 物件可重複渲染多次

## 安裝

```bash
pip install odttpl
```

或使用 [uv](https://github.com/astral-sh/uv)：

```bash
uv add odttpl
```

需求：

- Python 3.8+
- `jinja2`
- `lxml`

## 快速開始

先在 LibreOffice Writer 建立範本：

```text
Hello, {{ name }}!

Your order contains {{ total }} items.
```

再用 Python 渲染：

```python
from odttpl import OdtTemplate

tpl = OdtTemplate("template.odt")
tpl.render({"name": "John", "total": 5})
tpl.save("output.odt")
```

## 範本語法與 ODF Shorthand

標準 Jinja2 語法可直接寫在範本裡：

| 語法 | 用途 |
| --- | --- |
| `{{ variable }}` | 輸出變數 |
| `{% for item in items %} ... {% endfor %}` | 迴圈 |
| `{% if condition %} ... {% endif %}` | 條件式 |

LibreOffice 常會把同一個 Jinja 標籤拆成多段 XML。`OdtTemplate.patch_xml()` 會在渲染前自動把這些碎片接回去。

當 Jinja 標籤需要控制整個 ODF 元素時，請使用 element shorthand：

| Shorthand | ODF 元素 | 常見用途 |
| --- | --- | --- |
| `{%tr` / `{{tr` | `<table:table-row>` | 表格列迴圈 |
| `{%tc` / `{{tc` | `<table:table-cell>` | 儲存格層級控制 |
| `{%p` / `{{p` | `<text:p>` | 段落層級條件或迴圈 |
| `{%s` / `{{s` | `<text:span>` | span 層級控制 |
| `{%li` / `{{li` | `<text:list-item>` | 清單項目迴圈 |
| `{{block` | `<text:p>` 佔位段落 | 從 Python 插入混合 block XML |

範例：

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

如果替換值本身要輸出自己的段落與清單，而不是插入到佔位段落裡，就用 `{{block content}}`。

## RichText 與 RichTextParagraph

`RichText` 用來在既有段落裡產生行內格式：

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

範本：

```text
{{ greeting }}
```

`RichText.add()` 支援：

- `style`：使用範本裡既有的具名字元樣式
- `bold`、`italic`、`underline`、`strike`
- `color`、`size`、`font`
- `superscript`、`subscript`

當 Python 需要輸出完整段落，而不是行內 span 時，請用 `RichTextParagraph`：

```python
from odttpl import OdtTemplate, RichText, RichTextParagraph

tpl = OdtTemplate("template.odt")

rp = RichTextParagraph(tpl)
rp.add(RichText(tpl, "Heading", bold=True), parastyle="Heading_20_1")
rp.add(RichText(tpl, "Body paragraph"))

tpl.render({"content": rp})
tpl.save("output.odt")
```

範本：

```text
{{p content }}
```

別名：

- `R` = `RichText`
- `RP` = `RichTextParagraph`

## Listing

`Listing` 會把一般文字中的控制字元轉成 ODF 安全 XML：

```python
from odttpl import OdtTemplate, Listing

tpl = OdtTemplate("template.odt")
tpl.render({"body": Listing("Line one\nLine two\nIndented\tvalue")})
tpl.save("output.odt")
```

控制字元對應：

| 字元 | 結果 |
| --- | --- |
| `\n` | `<text:line-break/>` |
| `\t` | `<text:tab/>` |
| `\a` | 開始新的段落 |
| `\f` | 插入 soft page break 並開始新的段落 |

## InlineImage

`InlineImage` 會把圖片寫入 `Pictures/`，再把對應 XML 插到輸出內容中：

```python
from odttpl import OdtTemplate, InlineImage

tpl = OdtTemplate("template.odt")
tpl.render({"logo": InlineImage(tpl, "logo.png", width="4cm")})
tpl.save("output.odt")
```

範本：

```text
{{ logo }}
```

補充：

- `width` 與 `height` 使用 ODF 長度字串，例如 `"4cm"`、`"2in"`
- 如果只給一個尺寸，且能讀到圖片尺寸資訊，另一個尺寸會自動按比例換算
- `anchor` 預設為 `"as-char"`，也可改成 `"paragraph"`、`"page"` 等值

## OdtSubdoc

使用 `new_subdoc()` 插入另一個 `.odt` 檔的本文：

```python
from odttpl import OdtTemplate

tpl = OdtTemplate("master.odt")
chapter = tpl.new_subdoc("chapter.odt")
tpl.render({"chapter": chapter})
tpl.save("output.odt")
```

範本：

```text
{{p chapter }}
```

自動處理的事情：

- 子文件的 auto styles 會加上 `odttpl_sd...` 前綴後併入主文件
- 子文件內的圖片會一起複製到輸出 ODT
- 每次 `render()` 都會重置 subdoc 狀態，避免多次渲染互相污染

目前限制：

- 若子文件中使用的是主文件不存在的具名段落或字元樣式，尚未做完整 named-style merge；LibreOffice 會回退到主文件預設樣式

## StructuredBlock

`StructuredBlock` 是 Python 端的 builder，適合用在輸出內容同時混有自由段落、巢狀編號清單、項目內續段，以及條列之間插入說明段落的情境。

範本：

```text
{{block content}}
```

Python：

```python
from odttpl import OdtTemplate, StructuredBlock

tpl = OdtTemplate("report.odt")
block = StructuredBlock(tpl)

block.add_paragraph("Findings:")
block.add_list_item("Authentication", level=1)
block.add_list_item("Password reset flow", level=2)
block.add_paragraph("Affects SSO and local accounts.", in_list_item=True)
block.add_paragraph("Standalone note between list segments.", margin_left="1cm")
block.add_list_item("Session pinning", level=2)  # 預設會續號
block.add_list_item("Restart this nested sequence", level=2, continue_numbering=False)
block.close_list()
block.add_paragraph("Summary after the list.")

tpl.render({"content": block})
tpl.save("output.odt")
```

行為重點：

- `add_paragraph(..., in_list_item=True)` 會在目前的 `<text:list-item>` 裡再加一個段落
- `add_paragraph(..., in_list_item=False)` 會建立獨立的兄弟段落
- 如果用獨立段落把清單切開，下一個相容的 `add_list_item()` 預設會續接原本的編號
- `continue_numbering=False` 會改成重新開一段新的清單 segment
- `continue_numbering=True` 只有在存在相容的 suspended list context 時才合法
- `close_list()` 會同時清除 live list context 與可續接的 suspended context

### 自訂清單樣式

`NumberedListStyle` 用來定義程式化編號清單：

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

`BulletListStyle` 用來定義項目符號清單：

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

如果想直接沿用範本裡已存在的具名清單樣式，也可以直接傳字串：

```python
block = StructuredBlock(tpl, default_list_style="WWNum1")
```

傳字串時會直接使用該樣式名稱，不會由 `odttpl` 幫你自動註冊或重建該樣式。

block 內的段落樣式：

- `parastyle="Heading_20_1"`：使用範本中既有段落樣式
- `margin_left=` 與 `text_indent=`：若未指定 `parastyle`，會自動產生 paragraph style
- `add_paragraph()` 與 `add_list_item()` 都可以直接接收 `RichText`

別名：

- `SB` = `StructuredBlock`
- `NLS` = `NumberedListStyle`

## 進階用法

自動跳脫：

```python
tpl.render(context, autoescape=True)
```

自訂 Jinja 環境：

```python
from jinja2 import Environment

env = Environment()
env.filters["currency"] = lambda v: f"${v:,.2f}"

tpl.render(context, jinja_env=env)
```

檢查未宣告變數：

```python
variables = tpl.get_undeclared_variables()
```

同一個 template 物件多次渲染：

```python
tpl = OdtTemplate("template.odt")

for record in records:
    tpl.render(record)
    tpl.save(f"output_{record['id']}.odt")
```

每次 `render()` 都會回到原始 template bytes，並重置每次渲染使用的樣式、圖片與 subdoc registry。

## API 一覽

| API | 用途 |
| --- | --- |
| `OdtTemplate(template_file)` | 從路徑、`Path` 或 file-like 物件載入範本 |
| `OdtTemplate.render(context, jinja_env=None, autoescape=False)` | 渲染 `content.xml` 與可選的 `styles.xml` |
| `OdtTemplate.save(output_file)` | 將渲染結果寫到路徑或 file-like 物件 |
| `OdtTemplate.get_undeclared_variables()` | 掃描範本中的未宣告 Jinja 變數 |
| `OdtTemplate.new_subdoc(path=None)` | 建立綁定於模板的 `OdtSubdoc` |
| `RichText`、`R` | 建立行內格式化文字 |
| `RichTextParagraph`、`RP` | 建立一個或多個完整段落 |
| `Listing` | 將控制字元轉成 ODF 安全 XML |
| `InlineImage` | 嵌入圖片到輸出封裝 |
| `OdtSubdoc` | 表示在渲染時合併的子文件 |
| `StructuredBlock`、`SB` | 建立混合段落與清單輸出 |
| `NumberedListStyle`、`NLS` | 在 Python 中定義編號清單樣式 |
| `BulletListStyle` | 在 Python 中定義項目符號樣式 |
| `LevelSpec`、`BulletLevelSpec`、`LabelFollowedBy` | 設定清單樣式層級 |
| `StructuredBlockError` | 無效 block 建構流程時拋出的例外 |

## 開發

```bash
git clone http://192.168.100.213:3000/scbmark/python-odt-template.git
cd python-odt-template
uv venv
uv pip install -e ".[dev]"
uv run pytest tests/ -v
```

目前這份文件已和既有自動化測試對齊，重點依據 `tests/test_template.py` 與 `tests/test_structured_block.py` 的行為整理。

## 授權

本專案採用 [GNU Lesser General Public License v2.1](LICENSE.txt)。
