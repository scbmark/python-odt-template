# python-odf-template

以 [Jinja2](https://jinja.palletsprojects.com/) 為引擎，將 LibreOffice `.odt`（及其他 ODF 格式）文件當作範本來渲染，概念與用法均仿照 [python-docx-template](https://github.com/elapouya/python-docx-template)。

---

## 目錄

- [安裝](#安裝)
- [快速入門](#快速入門)
- [製作 ODF 範本](#製作-odf-範本)
- [Jinja2 標籤快捷語法](#jinja2-標籤快捷語法)
- [RichText 格式化文字](#richtext-格式化文字)
- [Listing 多行文字](#listing-多行文字)
- [InlineImage 嵌入圖片](#inlineimage-嵌入圖片)
- [進階用法](#進階用法)
- [在其他專案中引用](#在其他專案中引用)

---

## 安裝

### 方式一：從本機路徑安裝（開發中使用）

如果你的其他專案與本專案放在同一台機器上，可以直接以**可編輯模式**安裝：

```bash
# 使用 uv（推薦）
uv add --editable /path/to/python-odf-template

# 或使用 pip
pip install -e /path/to/python-odf-template
```

這樣修改 `odftpl/` 的原始碼後，不需重新安裝即可立即生效。

### 方式二：複製原始碼至你的專案

如果你不想維護一個獨立的套件，可以直接把 `odftpl/` 資料夾整個複製到你的專案目錄下：

```
your_project/
├── odftpl/          ← 整個資料夾複製過來
│   ├── __init__.py
│   ├── template.py
│   ├── richtext.py
│   ├── listing.py
│   └── inline_image.py
├── your_script.py
└── ...
```

然後確認安裝依賴：

```bash
uv add jinja2 lxml
# 或
pip install jinja2 lxml
```

### 方式三：安裝為 wheel 套件

先在本專案內打包：

```bash
cd /path/to/python-odf-template
uv build
```

會在 `dist/` 資料夾生成 `odftpl-0.1.0-py3-none-any.whl`，然後在目標專案中安裝：

```bash
uv add /path/to/python-odf-template/dist/odftpl-0.1.0-py3-none-any.whl
# 或
pip install /path/to/python-odf-template/dist/odftpl-0.1.0-py3-none-any.whl
```

---

## 快速入門

### 1. 準備範本 `template.odt`

用 LibreOffice Writer 開啟一個新文件，輸入以下內容並儲存為 `template.odt`：

```
您好，{{ name }}！

您的訂單共有 {{ total }} 項商品。
```

### 2. 撰寫 Python 程式

```python
from odftpl import OdfTemplate

tpl = OdfTemplate("template.odt")

context = {
    "name": "王小明",
    "total": 5,
}

tpl.render(context)
tpl.save("output.odt")
```

### 3. 執行後用 LibreOffice 開啟 `output.odt` 即可看到渲染結果。

---

## 製作 ODF 範本

在 LibreOffice Writer 中直接輸入 Jinja2 標籤即可，例如：

- **變數**：`{{ variable_name }}`
- **迴圈**：`{% for item in items %}` … `{% endfor %}`
- **條件**：`{% if condition %}` … `{% endif %}`

> **注意**：LibreOffice 在儲存時可能會把 `{{ variable }}` 拆成多個 XML 節點。
> `OdfTemplate.patch_xml()` 會自動處理這種情況，使用者無需擔心。

---

## Jinja2 標籤快捷語法

ODF XML 有嚴格的巢狀結構。當你需要用 Jinja2 控制整個**表格列**或**段落**時，
需要在對應 XML 元素**內部**加上帶前綴的標籤，讓 `patch_xml` 把整個元素替換為純 Jinja2 標籤。

### 表格列迴圈（`{%tr ... %}`）

在 LibreOffice 建立一個兩欄的表格，於**第一列**放置起始標籤，**資料列**放變數，**最後一列**放結束標籤：

| （迴圈控制列）            | （空白）     |
|--------------------------|-------------|
| `{%tr for item in rows %}` |            |
| `{{ item.name }}`        | `{{ item.price }}` |
| `{%tr endfor %}`          | （空白）     |

- 第一列與最後一列（含 `{%tr ... %}`）在渲染後會被移除，只剩中間的資料列重複。
- 若表格只有單欄，`{%tr ... %}` 可直接放在儲存格的段落內。

### 段落層級條件（`{%p ... %}`）

```
{%p if show_section %}
這整段只有在 show_section 為 True 時才會出現。
{%p endif %}
```

- 含 `{%p ... %}` 的段落本身在渲染後消失，只剩中間的段落受條件控制。

### 其他快捷前綴

| 前綴 | 對應 ODF 元素 | 典型用途 |
|------|--------------|---------|
| `{%tr` / `{{tr` | `<table:table-row>` | 表格列迴圈 |
| `{%tc` / `{{tc` | `<table:table-cell>` | 儲存格層級控制 |
| `{%p`  / `{{p`  | `<text:p>` | 段落層級條件／迴圈 |
| `{%s`  / `{{s`  | `<text:span>` | 文字區間層級控制 |

---

## RichText 格式化文字

使用 `RichText` 可以在同一個變數中混合多種格式：

```python
from odftpl import OdfTemplate, RichText

tpl = OdfTemplate("template.odt")

rt = RichText(tpl)
rt.add("一般文字，")
rt.add("粗體", bold=True)
rt.add("，")
rt.add("紅色斜體", italic=True, color="#CC0000")
rt.add("，")
rt.add("大字", size=18)

tpl.render({"greeting": rt})
tpl.save("output.odt")
```

範本中寫：`{{ greeting }}`

### `RichText.add()` 參數一覽

| 參數 | 型別 | 說明 |
|------|------|------|
| `text` | str | 文字內容 |
| `style` | str | 使用範本內已存在的**具名字元樣式** |
| `bold` | bool | 粗體 |
| `italic` | bool | 斜體 |
| `underline` | bool / str | 底線，可指定樣式如 `"dotted"`, `"solid"` |
| `strike` | bool | 刪除線 |
| `color` | str | 字色，十六進位如 `"#FF0000"` |
| `size` | int / float | 字級（單位：pt） |
| `font` | str | 字體名稱，如 `"Noto Sans TC"` |
| `superscript` | bool | 上標 |
| `subscript` | bool | 下標 |

### `RichTextParagraph` 跨段落格式

當你需要從 Python **輸出整個段落**（含段落樣式），使用 `RichTextParagraph`，
並在範本中使用 `{{p greeting }}` 取代整個段落：

```python
from odftpl import OdfTemplate, RichText, RichTextParagraph

tpl = OdfTemplate("template.odt")

rp = RichTextParagraph(tpl)
rp.add(RichText(tpl, "標題文字", bold=True), parastyle="Heading_20_1")
rp.add(RichText(tpl, "內文段落"))

tpl.render({"content": rp})
tpl.save("output.odt")
```

---

## Listing 多行文字

當你的字串包含換行、Tab，而你又不想自行組 XML，使用 `Listing`：

```python
from odftpl import OdfTemplate, Listing

tpl = OdfTemplate("template.odt")

text = "第一行\n第二行\n第三行"

tpl.render({"body": Listing(text)})
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
from odftpl import OdfTemplate, InlineImage

tpl = OdfTemplate("template.odt")

context = {
    "logo": InlineImage(tpl, "logo.png", width="4cm", height="2cm"),
}

tpl.render(context)
tpl.save("output.odt")
```

範本中寫：`{{ logo }}`（放在一個段落內）

`InlineImage` 會自動：
1. 將圖片檔案嵌入 ODF ZIP 的 `Pictures/` 目錄
2. 更新 `META-INF/manifest.xml`
3. 生成對應的 `<draw:frame>` XML

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `tpl` | OdfTemplate | 父範本物件 |
| `image_descriptor` | str / Path / file-like | 圖片路徑或 BytesIO |
| `width` | str | 寬度，如 `"5cm"`, `"2in"` |
| `height` | str | 高度，如 `"3cm"` |
| `anchor` | str | 錨點類型，預設 `"as-char"`（行內）；`"paragraph"` 為段落錨點 |

---

## 進階用法

### 自動跳脫（autoescape）

若你的資料來自使用者輸入，建議啟用 `autoescape` 避免 XML 注入：

```python
tpl.render(context, autoescape=True)
```

### 自訂 Jinja2 環境

可傳入自訂的 `jinja2.Environment` 以新增過濾器、測試或擴充功能：

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

### 多次渲染同一個 OdfTemplate 物件

```python
tpl = OdfTemplate("template.odt")

for record in records:
    tpl.render(record)
    tpl.save(f"output_{record['id']}.odt")
```

每次呼叫 `render()` 都會從原始範本重新渲染，不會互相污染。

---

## 在其他專案中引用

### 以 uv 管理的專案（推薦）

在你的目標專案根目錄執行：

```bash
# 從本機路徑直接引用（可隨時修改 odftpl 原始碼）
uv add --editable /path/to/python-odf-template

# 或先 build 成 wheel 再安裝
uv add /path/to/python-odf-template/dist/odftpl-0.1.0-py3-none-any.whl
```

`pyproject.toml` 中會自動加上：

```toml
[tool.uv.sources]
odftpl = { path = "/path/to/python-odf-template", editable = true }
```

### 以 pip 管理的專案

```bash
pip install -e /path/to/python-odf-template
```

### 確認安裝成功

```python
import odftpl
print(odftpl.__version__)  # 0.1.0
```

---

## 開發與測試

```bash
cd /path/to/python-odf-template

# 建立虛擬環境並安裝開發依賴
uv venv
uv pip install -e ".[dev]"

# 生成測試用範本（只需執行一次）
uv run python tests/make_templates.py

# 執行測試
uv run pytest tests/ -v
```
