# python-odt-template

[English](README.md) | 繁體中文

> [!WARNING]
> 本專案由 AI 輔助開發（Vibe Coding）。程式碼未經完整人工審查，可能存在錯誤、安全漏洞或非預期行為。**請勿在生產環境中使用，風險自負。** 歡迎提交 Issue 或 PR 協助改善。

[![PyPI version](https://img.shields.io/pypi/v/odttpl.svg)](https://pypi.org/project/odttpl/)
[![Python versions](https://img.shields.io/pypi/pyversions/odttpl.svg)](https://pypi.org/project/odttpl/)
[![License: LGPL v2.1](https://img.shields.io/badge/License-LGPL_v2.1-blue.svg)](LICENSE.txt)
[![Tests](https://github.com/yourname/python-odt-template/actions/workflows/test.yml/badge.svg)](https://github.com/yourname/python-odt-template/actions)

以 [Jinja2](https://jinja.palletsprojects.com/) 為引擎，用 LibreOffice `.odt` 文件作為範本來渲染文件。概念與用法仿照 [python-docx-template](https://github.com/elapouya/python-docx-template)，但針對 ODF 格式重新實作。

---

## 特色

- **Jinja2 全支援**：在 `.odt` 範本中直接使用變數、迴圈、條件等語法
- **XML 自動修復**：LibreOffice 儲存時可能拆分標籤，`patch_xml()` 自動還原
- **表格列 / 段落 / 清單項目層級控制**：`{%tr`、`{%p`、`{%li` 等快捷前綴可操控整個 ODF 元素
- **渲染後自動 well-formed 檢查**：每次渲染完成後會驗證輸出 XML；若 Jinja 標籤跨越 ODF 元素邊界，錯誤訊息會指出應改用哪個 shorthand
- **RichText**：在同一變數中混合粗體、斜體、顏色、字級等格式
- **Listing**：多行文字含換行、Tab、分頁的完整處理
- **InlineImage**：嵌入圖片並自動更新 manifest
- **Subdoc**：將另一個 `.odt` 檔的內文嵌入主範本，樣式與圖片自動合併
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
| `{%li` / `{{li` | `<text:list-item>` | 項目符號／編號清單迴圈 |

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

### 清單項目迴圈（`{%li`）

若 Jinja `{% for %}` 跨越 `<text:list-item>` 邊界，每次展開都會開啟一個新的 `<text:list-item>` 而不關閉前一個，導致 XML 失衡。使用 `{%li` 可將迴圈錨定在 list-item 元素本身。

在 LibreOffice Writer 中建立一個項目符號或編號清單，**放三個兄弟項目**（第一、三項作為 sentinel，渲染後會被移除）：

```
• {%li for item in items %}
• {{ item }}
• {%li endfor %}
```

渲染後只有中間那個 list-item 會依 `items` 重複展開，產生同一個 `<text:list>` 下連續的兄弟 `<text:list-item>`（自動編號得以連續）。

> 若 for-loop 仍跨越 `<text:list-item>` 邊界而未使用 `{%li`，`render()` 會拋出 `ValueError: Rendered content.xml is not well-formed XML …`，並在訊息中建議對應的 shorthand。

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

## Subdoc — 嵌入其他 ODT 檔案

使用 `new_subdoc()` 將另一個 `.odt` 檔案的內文嵌入主範本。子文件的段落樣式與嵌入圖片會自動合併到輸出檔中。

```python
from odttpl import OdtTemplate

tpl = OdtTemplate("main.odt")
sub = tpl.new_subdoc("chapter.odt")
tpl.render({"chapter": sub})
tpl.save("output.odt")
```

在主範本中，於想插入子文件的位置單獨放一個段落，內容寫 `{{p chapter }}`。必須使用 `{{p` 前綴，這樣整個佔位段落才會被替換。

### 嵌入多個子文件

```python
tpl = OdtTemplate("main.odt")
intro = tpl.new_subdoc("intro.odt")
body  = tpl.new_subdoc("body.odt")
tpl.render({"intro": intro, "body": body})
tpl.save("output.odt")
```

### 注意事項

- **樣式合併**：子文件中的自動樣式（段落、字元等）會加上唯一前綴後注入主文件，避免命名衝突。
- **圖片合併**：子文件中的嵌入圖片會自動複製到輸出的 ZIP 壓縮包中。
- **範本變數**：子文件是一般的 `.odt` 檔，其中的 Jinja2 標籤**不會**被渲染，只有內文 XML 會被插入。

---

## StructuredBlock — 以 Python 組出段落＋巢狀清單

當輸出需要混合自由段落、多層編號／項目符號清單、以及插在清單項目中間的補充段落時，靜態範本（即使搭配 `{%li %}` 迴圈）常難以表達。`StructuredBlock` 是一組 Python 端的 builder：你在程式中宣告完整結構，一次渲染後，再填入範本中的 `{{block VAR}}` 佔位符。

### 基本範例 — 混合段落與巢狀清單

**範本**（`report.odt` 內容）：

```xml
<text:p>報告：</text:p>
<text:p>{{block content}}</text:p>
<text:p>— 結束 —</text:p>
```

`{{block VAR}}` 快捷會先剝除外層 `<text:p>` 佔位符，再插入 builder 產出的 XML — 因此 block 本身可以輸出 `<text:p>` 與 `<text:list>` 混合的兄弟節點。

**Python：**

```python
from odttpl import OdtTemplate, StructuredBlock

tpl = OdtTemplate("report.odt")
block = StructuredBlock(tpl)
block.add_paragraph("發現項目：")
block.add_list_item("身份驗證", level=1)
block.add_list_item("密碼重設失效", level=2)
block.add_paragraph("同時影響 SSO 與本地帳號。", in_list_item=True)
block.add_list_item("Session pinning", level=2)
block.add_list_item("授權", level=1)

tpl.render({"content": block})
tpl.save("out.odt")
```

`add_paragraph(..., in_list_item=True)` 會把該段落作為「延伸段落」附加到目前開啟的清單項目中（輸出為同一 `<text:list-item>` 內的第二個 `<text:p>`）。未帶 `in_list_item=True` 的 `add_paragraph` 則會先關閉當前清單上下文。

### 自訂 `NumberedListStyle`

未指定 `list_style` 時，block 會自動註冊一份 5 層、`1./1.1./1.1.1.` 的編號樣式，名稱為 `odttpl_L{n}`。若要自訂：

```python
from odttpl import StructuredBlock, NumberedListStyle, LevelSpec

numbering = NumberedListStyle(
    tpl,
    levels=[
        LevelSpec(format="A", suffix=")"),      # A) B) C) …
        LevelSpec(format="一", suffix="、"),     # 一、二、三、…
        LevelSpec(format="1", suffix=".",       # 1. 2. 3. …
                  display_levels=1),
    ],
)
block = StructuredBlock(tpl, default_list_style=numbering)
```

`LevelSpec.format` 接受 ODF 的 `style:num-format`（`"1"`、`"a"`、`"A"`、`"i"`、`"I"`、`"一"`、或 `""`）。使用 `format="一"` 可產生中文小寫數字（`一、二、三、…`）；輸出 ODT 時會轉成 LibreOffice 相容的 CJK 編號格式。`display_levels=2` 於第二層會產出串接標籤，如 `1.1.`。

### `BulletListStyle`

項目符號清單用 `BulletListStyle`。可接受 `BulletLevelSpec`、dict、或純符號字串：

```python
from odttpl import StructuredBlock, BulletListStyle, BulletLevelSpec

bullets = BulletListStyle(tpl, levels=["•", "◦", "▪"])
# 或：BulletListStyle(tpl, levels=[BulletLevelSpec(bullet_char="•", space_before="1cm")])

block = StructuredBlock(tpl, default_list_style=bullets)
block.add_list_item("one", level=1)
block.add_list_item("one-a", level=2)
```

### 使用範本中既有的具名清單樣式

若 `.odt` 中已定義好所需的清單樣式，直接以字串傳入，不會另外註冊：

```python
block = StructuredBlock(tpl, default_list_style="MyTemplateListStyle")
```

### 段落縮排

`add_paragraph` 接受 `margin_left` 與 `text_indent`（ODF 長度字串如 `"2cm"`、`"-0.5cm"`）。系統會自動產生段落自動樣式並注入 `<office:automatic-styles>`。若同時指定 `parastyle=`，以 `parastyle` 為準、忽略縮排參數：

```python
block.add_paragraph("縮排備註", margin_left="2cm", text_indent="-0.5cm")
```

### 在 block 中使用 `RichText`

`add_paragraph` 與 `add_list_item` 皆接受 `str` 或 `RichText`。`RichText` 註冊的字元樣式會照常注入：

```python
from odttpl import RichText
block.add_list_item(RichText(tpl, "CRITICAL", bold=True, color="#CC0000"))
```

### 與 `{%li %}` 迴圈並存

同一份範本可混用 `{{block VAR}}` 與 `{%li for … %}`，互不干擾。

### 驗證

`StructuredBlock` 會在下列情況丟出 `StructuredBlockError`：
- `level < 1`
- 跳級（例如 level 1 直接跳到 level 3、缺了中間的 level 2）
- 在無開啟清單項目時呼叫 `add_paragraph(in_list_item=True)`

渲染後的 XML 仍會經過 `_check_well_formed`，結構錯誤會以描述清楚的 `ValueError` 拋出。

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
