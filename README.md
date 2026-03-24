# python-odt-template

[English](README.en.md) | 繁體中文

[![PyPI version](https://img.shields.io/pypi/v/odttpl.svg)](https://pypi.org/project/odttpl/)
[![Python versions](https://img.shields.io/pypi/pyversions/odttpl.svg)](https://pypi.org/project/odttpl/)
[![License: LGPL v2.1](https://img.shields.io/badge/License-LGPL_v2.1-blue.svg)](LICENSE.txt)
[![Tests](https://github.com/yourname/python-odt-template/actions/workflows/test.yml/badge.svg)](https://github.com/yourname/python-odt-template/actions)

以 [Jinja2](https://jinja.palletsprojects.com/) 為引擎，用 LibreOffice `.odt` 文件作為範本來渲染文件。概念與用法仿照 [python-docx-template](https://github.com/elapouya/python-docx-template)，但針對 ODF 格式重新實作。

---

## 特色

- **Jinja2 全支援**：在 `.odt` 範本中直接使用變數、迴圈、條件等語法
- **XML 自動修復**：LibreOffice 儲存時可能拆分標籤，`patch_xml()` 自動還原
- **表格列 / 段落層級控制**：`{%tr`, `{%p` 等快捷前綴可操控整個 ODF 元素
- **RichText**：在同一變數中混合粗體、斜體、顏色、字級等格式
- **Listing**：多行文字含換行、Tab、分頁的完整處理
- **InlineImage**：嵌入圖片並自動更新 manifest
- **多次渲染**：同一 `OdtTemplate` 物件可重複渲染不同資料

---

## 安裝

```bash
pip install odttpl
```

或使用 [uv](https://github.com/astral-sh/uv)：

```bash
uv add odttpl
```

**需求**：Python 3.8+，依賴 `jinja2` 與 `lxml`（自動安裝）。

---

## 快速入門

**1. 準備範本 `template.odt`**

在 LibreOffice Writer 中輸入以下內容並儲存：

```
您好，{{ name }}！

您的訂單共有 {{ total }} 項商品。
```

**2. 渲染並輸出**

```python
from odttpl import OdtTemplate

tpl = OdtTemplate("template.odt")
tpl.render({"name": "王小明", "total": 5})
tpl.save("output.odt")
```

**3. 用 LibreOffice 開啟 `output.odt`** 即可看到渲染結果。

---

## 製作 ODF 範本

在 LibreOffice Writer 中直接輸入 Jinja2 標籤：

| 語法 | 用途 |
|------|------|
| `{{ variable }}` | 輸出變數 |
| `{% for item in items %}` … `{% endfor %}` | 迴圈 |
| `{% if condition %}` … `{% endif %}` | 條件 |

> **注意**：LibreOffice 儲存時可能將 `{{ variable }}` 拆成多個 XML 節點。
> `OdtTemplate` 會在載入時自動呼叫 `patch_xml()` 修正，使用者無需處理。

---

## Jinja2 標籤快捷語法

ODF XML 有嚴格的巢狀結構。若要用 Jinja2 控制整個**表格列**或**段落**，需在對應 XML 元素內部加上帶前綴的標籤，`patch_xml` 會把整個元素替換為純 Jinja2 標籤。

| 前綴 | 對應 ODF 元素 | 典型用途 |
|------|--------------|---------|
| `{%tr` / `{{tr` | `<table:table-row>` | 表格列迴圈 |
| `{%tc` / `{{tc` | `<table:table-cell>` | 儲存格層級控制 |
| `{%p` / `{{p` | `<text:p>` | 段落層級條件／迴圈 |
| `{%s` / `{{s` | `<text:span>` | 文字區間層級控制 |

### 表格列迴圈（`{%tr`）

在 LibreOffice 建立一個兩欄表格：

| 欄位 A | 欄位 B |
|-------|-------|
| `{%tr for item in rows %}` | （空白） |
| `{{ item.name }}` | `{{ item.price }}` |
| `{%tr endfor %}` | （空白） |

含 `{%tr` 的列在渲染後會被移除，只剩資料列重複輸出。

### 段落層級條件（`{%p`）

```
{%p if show_section %}
這整段只有在 show_section 為 True 時才會出現。
{%p endif %}
```

含 `{%p` 的段落本身在渲染後消失。

---

## RichText 格式化文字

使用 `RichText`（縮寫 `R`）可在同一變數中混合多種格式：

```python
from odttpl import OdtTemplate, RichText

tpl = OdtTemplate("template.odt")

rt = RichText(tpl)
rt.add("一般文字，")
rt.add("粗體", bold=True)
rt.add("紅色斜體", italic=True, color="#CC0000")
rt.add("大字", size=18)

tpl.render({"greeting": rt})
tpl.save("output.odt")
```

範本中寫：`{{ greeting }}`

### `RichText.add()` 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `text` | str | 文字內容 |
| `style` | str | 範本內已存在的具名字元樣式 |
| `bold` | bool | 粗體 |
| `italic` | bool | 斜體 |
| `underline` | bool / str | 底線；可指定樣式如 `"dotted"`, `"solid"` |
| `strike` | bool | 刪除線 |
| `color` | str | 字色，十六進位如 `"#FF0000"` |
| `size` | int / float | 字級（pt） |
| `font` | str | 字體名稱，如 `"Noto Sans TC"` |
| `superscript` | bool | 上標 |
| `subscript` | bool | 下標 |

### RichTextParagraph — 跨段落格式

若需從 Python 輸出含段落樣式的整個段落，使用 `RichTextParagraph`（縮寫 `RP`），並在範本中以 `{{p content }}` 取代整個段落：

```python
from odttpl import OdtTemplate, RichText, RichTextParagraph

tpl = OdtTemplate("template.odt")

rp = RichTextParagraph(tpl)
rp.add(RichText(tpl, "標題文字", bold=True), parastyle="Heading_20_1")
rp.add(RichText(tpl, "內文段落"))

tpl.render({"content": rp})
tpl.save("output.odt")
```

---

## Listing 多行文字

當字串包含換行、Tab，而不想自行組 XML 時使用 `Listing`：

```python
from odttpl import OdtTemplate, Listing

tpl = OdtTemplate("template.odt")
tpl.render({"body": Listing("第一行\n第二行\n第三行")})
tpl.save("output.odt")
```

| 特殊字元 | 渲染結果 |
|---------|---------|
| `\n` | 段落內換行（`<text:line-break/>`） |
| `\t` | Tab 停格（`<text:tab/>`） |
| `\a` | 開始新段落（沿用相同段落樣式） |
| `\f` | 軟分頁後開始新段落 |

---

## InlineImage 嵌入圖片

```python
from odttpl import OdtTemplate, InlineImage

tpl = OdtTemplate("template.odt")
tpl.render({"logo": InlineImage(tpl, "logo.png", width="4cm", height="2cm")})
tpl.save("output.odt")
```

範本中寫：`{{ logo }}`（放在一個段落內）

`InlineImage` 會自動：
1. 將圖片嵌入 ODF ZIP 的 `Pictures/` 目錄
2. 更新 `META-INF/manifest.xml`
3. 產生對應的 `<draw:frame>` XML

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `tpl` | OdtTemplate | 父範本物件 |
| `image_descriptor` | str / Path / file-like | 圖片路徑或 BytesIO |
| `width` | str | 寬度，如 `"5cm"`, `"2in"` |
| `height` | str | 高度，如 `"3cm"` |
| `anchor` | str | 錨點類型，預設 `"as-char"`（行內）；`"paragraph"` 為段落錨點 |

---

## 進階用法

### 自動跳脫（autoescape）

若資料來自使用者輸入，建議啟用 `autoescape` 防止 XML 注入：

```python
tpl.render(context, autoescape=True)
```

### 自訂 Jinja2 環境

傳入自訂的 `jinja2.Environment` 以新增過濾器或擴充功能：

```python
from jinja2 import Environment

env = Environment()
env.filters["currency"] = lambda v: f"NT${v:,.0f}"

tpl.render(context, jinja_env=env)
```

### 查詢範本中的未宣告變數

```python
variables = tpl.get_undeclared_variables()
print(variables)  # {'name', 'total', 'items', ...}
```

### 多次渲染

```python
tpl = OdtTemplate("template.odt")

for record in records:
    tpl.render(record)
    tpl.save(f"output_{record['id']}.odt")
```

每次呼叫 `render()` 都會從原始範本重新渲染，不會互相污染。

---

## 開發

```bash
git clone https://github.com/yourname/python-odt-template.git
cd python-odt-template

# 建立虛擬環境並安裝開發依賴
uv venv && uv pip install -e ".[dev]"

# 執行測試
uv run pytest tests/ -v
```

歡迎提交 Issue 與 Pull Request！

---

## 授權

本專案採用 [GNU Lesser General Public License v2.1](LICENSE.txt)，與 [python-docx-template](https://github.com/elapouya/python-docx-template) 相同。
