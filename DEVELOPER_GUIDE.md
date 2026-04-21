# odttpl 開發者指南

這份文件說明 `odttpl` 目前的實作模型、渲染流程與測試基線，內容以 2026-04-21 當下專案中的程式碼與既有測試為準。

## 專案概述

`odttpl` 把 ODF 文件當成 Jinja2 template 來處理。以最常見的 `.odt` 為例，實際流程是：

1. 讀取 ODT ZIP 內的 `content.xml`
2. 將 LibreOffice 拆碎的 Jinja 標籤重新修補
3. 用 Jinja2 以 Python context 渲染 XML
4. 注入渲染期間動態產生的樣式、圖片與 subdoc 內容
5. 把修改過的 XML 與新增資源寫回新的 ODT ZIP

目前文件與測試主要聚焦在 `.odt` 用法，但核心設計是 ODF XML 層級的 template engine。

## 目錄結構

```text
python-odt-template/
├─ odttpl/
│  ├─ __init__.py
│  ├─ template.py
│  ├─ richtext.py
│  ├─ listing.py
│  ├─ inline_image.py
│  ├─ subdoc.py
│  └─ structured_block.py
├─ tests/
│  ├─ test_template.py
│  ├─ test_structured_block.py
│  ├─ make_templates.py
│  └─ templates/
├─ README.md
├─ README.zh-TW.md
└─ pyproject.toml
```

模組分工：

- `template.py`：核心 `OdtTemplate`、XML patching、render/save、style/image/subdoc 注入
- `richtext.py`：`RichText`、`RichTextParagraph` 與行內/段落格式產生
- `listing.py`：多行文字與控制字元轉 ODF XML
- `inline_image.py`：圖片封裝與 `<draw:frame>` XML 產生
- `subdoc.py`：子文件 body、auto styles、圖片合併
- `structured_block.py`：以 Python builder 組出混合段落與巢狀清單

## 核心公開 API

`odttpl.__init__` 目前匯出的主要 API 如下：

- `OdtTemplate`
- `RichText`, `RichTextParagraph`, `R`, `RP`
- `Listing`
- `InlineImage`
- `OdtSubdoc`
- `StructuredBlock`, `SB`
- `NumberedListStyle`, `BulletListStyle`, `NLS`
- `LevelSpec`, `BulletLevelSpec`, `LabelFollowedBy`
- `StructuredBlockError`

## `template.py`：核心引擎

### `OdtTemplate`

建構子：

```python
OdtTemplate(template_file: Union[str, Path, IO[bytes]])
```

重要狀態：

- `_template_data`：原始 ZIP bytes，整個 render 週期都以它為 source of truth
- `_modified_files`：這次 render 需要覆蓋回 ZIP 的檔案內容
- `_extra_images`：由 `InlineImage` 或 subdoc 合併帶入的額外圖片
- `_auto_styles`：文字樣式 registry，key 是 style props 的 `frozenset`
- `_list_styles`：清單樣式 registry，key 是 style name，value 是 `NumberedListStyle` 或 `BulletListStyle`
- `_para_styles`：段落樣式 registry，用於 `StructuredBlock` 的自動 paragraph styles
- `_subdoc_list`：本次 render 中實際被引用到的 subdoc
- `_subdoc_counter`：subdoc 前綴計數器，生成 `odttpl_sd1_...`

### 重要方法

- `render(context, jinja_env=None, autoescape=False)`
- `save(output_file)`
- `patch_xml(src_xml)`
- `build_content_xml(...)`
- `build_styles_xml(...)`
- `render_xml_part(...)`
- `resolve_listing(...)`
- `_merge_consecutive_lists(...)`
- `_inject_auto_styles(...)`
- `_register_text_style(...)`
- `_register_list_style(...)`
- `_register_para_style(...)`
- `new_subdoc(...)`
- `get_undeclared_variables(...)`

### `patch_xml()` 的角色

LibreOffice 會把 `{{ name }}` 或 `{% if ... %}` 之類的 Jinja 標籤拆到多個 `<text:span>` 甚至多個 XML node。`patch_xml()` 會先把這些碎片修回 Jinja2 可解析的字串，再交給 render。

它還會處理 element shorthand：

- `{%tr` / `{{tr` -> `<table:table-row>`
- `{%tc` / `{{tc` -> `<table:table-cell>`
- `{%p` / `{{p` -> `<text:p>`
- `{%s` / `{{s` -> `<text:span>`
- `{%li` / `{{li` -> `<text:list-item>`
- `{{block` -> `<text:p>` placeholder paragraph

`{{block ...}}` 是這次文件更新中特別要注意的點：它和 `StructuredBlock` 搭配使用，會先移除包著 placeholder 的 `<text:p>`，讓 Python 端 builder 直接輸出自己的 `<text:p>` / `<text:list>` 兄弟節點。

### 樣式注入流程

render 期間可能出現三類自動樣式：

- 文字樣式：`RichText` 呼叫 `tpl._register_text_style(...)`
- 清單樣式：`NumberedListStyle` / `BulletListStyle` 呼叫 `tpl._register_list_style(...)`
- 段落樣式：`StructuredBlock` 在使用 `margin_left` / `text_indent` 時呼叫 `tpl._register_para_style(...)`

`render()` 在 `build_content_xml()` 之後，若 `_auto_styles`、`_list_styles`、`_para_styles` 任一非空，就會透過 `_inject_auto_styles()` 把這些 style XML 寫入 `<office:automatic-styles>`。

這是這個專案一個很重要的實作特性：style registry 是 per-render state，不是持久狀態。

### `render()` 的重置行為

每次 `render()` 開始都會清空：

- `_modified_files`
- `_extra_images`
- `_auto_styles`
- `_list_styles`
- `_para_styles`
- `_subdoc_list`
- `_subdoc_counter`

這保證同一個 `OdtTemplate` 物件可以安全地多次渲染，而不會把前一次的 style、image 或 subdoc 狀態殘留到下一次。

## `richtext.py`：文字與段落格式

### `RichText`

`RichText` 用來建立行內內容。它不直接把格式寫成 ODF inline property，而是透過 `tpl._register_text_style(...)` 先註冊一個 named automatic style，再在輸出的 `<text:span>` 上引用這個 style name。

設計重點：

- fragment 先存在 `_fragments`
- 真正的 style name 採 lazy registration，在 `_build()` 時才註冊
- 這樣做是因為 `render()` 會先清掉 `_auto_styles`，如果太早註冊，render 開始時會被洗掉

### `RichTextParagraph`

`RichTextParagraph` 直接產生完整 `<text:p>` XML，因此應搭配 `{{p var }}` 使用，而不是一般的 `{{ var }}`。

它本身不管理 paragraph automatic styles；如果需要指定段落樣式，使用 `parastyle=` 指向模板裡既有的 paragraph style name。

## `listing.py`：多行文字

`Listing` 的責任很單純：先把一般文字安全 escape，再把控制字元在 render 後轉成 ODF 對應元素。

對應關係：

- `\n` -> `<text:line-break/>`
- `\t` -> `<text:tab/>`
- `\a` -> 新段落
- `\f` -> `<text:soft-page-break/>` + 新段落

`Listing` 自己不直接修改 ZIP，也不涉及 style registry。

## `inline_image.py`：圖片嵌入

`InlineImage` 在 `__str__()` / `_build_xml()` 時做兩件事：

1. 透過 `tpl._add_image(...)` 把圖片內容註冊到 `_extra_images`
2. 產生 `<draw:frame><draw:image .../></draw:frame>` XML

重要行為：

- `image_descriptor` 可為檔案路徑、`Path` 或 file-like object
- 若只給 `width` 或 `height`，會嘗試讀取圖片尺寸並按比例推算另一邊
- `save()` 階段才真正把 `_extra_images` 寫入 ZIP 的 `Pictures/`
- `_update_manifest()` 會同步更新 `META-INF/manifest.xml`

## `subdoc.py`：子文件合併

`OdtSubdoc` 代表一個可在 render 時插入主文件的 `.odt` body。

典型流程：

1. `tpl.new_subdoc("chapter.odt")`
2. `OdtSubdoc._load()` 讀取子文件的 body、automatic styles、圖片
3. `render()` 時 `OdtSubdoc._reset()` 清空 per-render 狀態
4. `__str__()` / `_get_xml()` 觸發 `_ensure_renamed()`
5. automatic style names 改寫成 `odttpl_sd{n}_...`
6. 圖片路徑改寫成新的 `Pictures/odttpl_sd...`
7. `tpl._register_subdoc(self)` 將此 subdoc 加入本次 render 的合併清單

目前合併範圍：

- 子文件 body XML
- 子文件 automatic styles
- 子文件內嵌圖片

目前不做完整 merge 的部分：

- 子文件獨有的 named paragraph / character styles

## `structured_block.py`：程式化段落與巢狀清單

### 對外 API

主要類別與別名：

- `StructuredBlock` / `SB`
- `NumberedListStyle` / `NLS`
- `BulletListStyle`
- `LevelSpec`
- `BulletLevelSpec`
- `LabelFollowedBy`
- `StructuredBlockError`

主要方法：

- `add_paragraph(...)`
- `add_list_item(...)`
- `close_list()`

### 內部資料模型

AST 相關型別：

- `ParagraphNode`
- `ListItemNode`
- `_ListGroup`
- `_SuspendedListContext`

`StructuredBlock` 內部的重要欄位：

- `_nodes`：最上層輸出節點清單，內容是 `ParagraphNode` 或 `_ListGroup`
- `_list_stack`：目前 live 的 list path；索引 `i` 對應 level `i + 1`
- `_current_item`：目前可接受 continuation paragraph 的 list item
- `_suspended_list_context`：當 list 被 standalone paragraph 切斷時保留下來的可續接 ancestry
- `_referenced_styles`：此 block 用到的 list style objects，`_build()` 時會重新註冊
- `_default_style_obj`：lazy 建立的預設 numbered list style

### `add_paragraph()` 規則

`add_paragraph(text, ..., in_list_item=False)`：

- `in_list_item=True`：把段落加到目前 list item 的 `continuation`
- `in_list_item=False`：先把目前 live list context suspend 起來，再建立 standalone paragraph

錯誤情況：

- 若 `in_list_item=True` 但目前沒有 open list item，拋 `StructuredBlockError`

### `add_list_item()` 規則

`add_list_item(text, ..., level=1, list_style=None, continue_numbering=None)`：

- `level < 1` 直接拋錯
- 若跳層，例如從 level 1 直接加 level 3，也會拋錯
- `list_style` 可為：
  - `None`
  - 既有 template style name 字串
  - `NumberedListStyle`
  - `BulletListStyle`
- 若 block 沒指定 `default_list_style`，第一次需要時會 lazy 建立一個五層的預設 numbered style

### 清單續號與 restart 行為

這是 `StructuredBlock` 近期最重要的行為。

當清單被 standalone paragraph 切開時：

1. `_suspend_list_context()` 會記住目前每一層使用的 style name
2. 下一次 `add_list_item()` 若 target level 與 style 相容，就可透過 `_resume_suspended_context()` 重建 ancestry
3. 若 `continue_numbering` 沒特別指定，預設採續號
4. 若 `continue_numbering=False`，則在被恢復的那一層改為 restart
5. 若 `continue_numbering=True` 但不存在相容的 suspended context，會拋 `StructuredBlockError`

對 live list 也有 restart 規則：

- 若同層清單 item 指定 `continue_numbering=False`
- 或同層改用不同 `list_style`
- 會新開一個 sibling `_ListGroup`

輸出到 XML 時，每個 `_ListGroup` 會生成：

```xml
<text:list text:style-name="..." text:continue-numbering="true|false">
```

### `close_list()`

`close_list()` 會：

- 清掉 `_list_stack`
- 清掉 `_current_item`
- 清掉 `_suspended_list_context`

也就是說，它不只是關閉目前 live list，也會讓後續 `add_list_item(..., continue_numbering=True)` 失去可續接上下文。

### 清單樣式物件

#### `NumberedListStyle`

- `levels` 接受 `LevelSpec` 或 `dict`
- 建構時就會向 `tpl._register_list_style(self)` 註冊
- 若沒提供 `name`，會由 template 生成類似 `odttpl_L1` 的 style name
- `xml` property 會輸出 `<text:list-style>...</text:list-style>`

`LevelSpec` 重要欄位：

- `format`
- `suffix`
- `prefix`
- `display_levels`
- `first_line_indent`
- `indent_at`
- `label_followed_by`
- `tab_stop_at`
- `start_value`

`label_followed_by` 必須是 `LabelFollowedBy` enum 值；傳一般字串會在產生 XML 時拋 `StructuredBlockError`。

特殊格式：

- 中文數字格式會被正規化成 LibreOffice 相容的 CJK 數字格式字串

#### `BulletListStyle`

- `levels` 接受：
  - `BulletLevelSpec`
  - `dict`
  - 單純的 bullet 字元字串
- 空 levels 會拋 `StructuredBlockError`
- 和 `NumberedListStyle` 一樣，建立時就會註冊到 template

`BulletLevelSpec` 目前支援：

- `bullet_char`
- `space_before`
- `min_label_width`

### paragraph style registration

`StructuredBlock._render_paragraph()` 在遇到以下情況時會建立自動段落樣式：

- `parastyle` 未指定
- 但有 `margin_left` 或 `text_indent`

此時會呼叫：

```python
tpl._register_para_style(margin_left=..., text_indent=...)
```

如果同時給了 `parastyle`，就直接使用現有 style name，不再自動產生 paragraph style。

### `RichText` 與 block 的整合

`add_paragraph()` 和 `add_list_item()` 的 `text` 都接受 `str` 或 `RichText`。

在 block render 時：

- `RichText` 會透過 `_render_inline()` 呼叫 `_build()`
- `_build()` 內部再去註冊對應文字樣式
- 這些樣式最後跟其他 registry 一起注入 `<office:automatic-styles>`

## 渲染資料流

可把 `render()` 的高階流程理解成：

```text
load template bytes
-> reset per-render state
-> reset any OdtSubdoc found in context
-> build content.xml
   -> patch_xml()
   -> Jinja render
   -> resolve_listing()
   -> _merge_consecutive_lists()
   -> _check_well_formed()
-> inject automatic styles if needed
-> merge subdoc auto styles and images
-> optionally build styles.xml
-> update manifest for added images
-> save()
```

幾個值得特別記住的點：

- `RichText`、`StructuredBlock`、`InlineImage`、`OdtSubdoc` 都是靠 Jinja render 過程中的 `__str__()` / `__html__()` 參與輸出
- 真正寫入 ZIP 的時機在 `save()`，不是在 `render()`
- `save()` 會保留原 ZIP 內未變動的檔案，只替換 `_modified_files` 以及新增的 `Pictures/*`

## XML 正確性與錯誤模型

render 之後 `content.xml` 會再跑 `_check_well_formed()`。如果 Jinja 標籤跨越了不合法的 ODF 邊界，就會收到描述性的 `ValueError`，訊息會提示改用 `{%tr %}`、`{%tc %}`、`{%p %}`、`{%s %}`、`{%li %}` 等 shorthand。

這個檢查是保護專案穩定性的重要防線，因為很多錯誤若等到 LibreOffice 開啟文件時才爆出來，回溯起來會很痛苦。

## 測試基線

本文件更新時，已驗證：

```bash
uv run pytest tests/test_template.py tests/test_structured_block.py -q
```

結果為 `61 passed`。

### `tests/test_template.py`

目前覆蓋的主題：

- 基本變數替換
- `autoescape=True`
- `{%tr` 表格列迴圈
- `Listing` 的換行與 tab
- `RichText` 的粗體、顏色、named style、跨段落切分
- `{%p` 條件式
- `get_undeclared_variables()`
- `save()` 到檔案
- 同一 template 多次 render
- loop 展開後連續清單的續號邏輯
- `OdtSubdoc` 的基本插入、auto style merge、style name collision 避免、多次 render 穩定性
- `patch_xml()` 對 `&quot;`、`&apos;`、`&amp;`、`&#160;` 等 entity 的清理邏輯

### `tests/test_structured_block.py`

目前覆蓋的主題：

- 純段落 block
- 段落與清單交錯輸出
- 三層巢狀 numbered list
- list item 內 continuation paragraphs
- block 中使用 `RichText`
- level skip / invalid level / orphan continuation 的錯誤情況
- 預設清單樣式自動註冊
- 使用 template 既有具名清單樣式
- `NumberedListStyle` 自訂 levels
- LibreOffice label alignment 相關 XML
- 自訂 tab stop
- `LabelFollowedBy` 型別驗證
- 中文數字格式輸出
- block 與 `{%li %}` 同時存在
- split paragraph 後的續號 / restart 行為
- `close_list()` 對 suspended context 的清除
- `margin_left` / `text_indent` 觸發 paragraph style registration
- `BulletListStyle`
- block 插入 table cell

## 擴充建議

如果要新增新能力，優先遵守這幾個原則：

- 盡量把 registry 設計維持為 per-render state
- 讓新型別在 Jinja render 期間才做 lazy registration，避免被 `render()` 一開始的 reset 洗掉
- 新增 shorthand 或 patch 規則時，務必用最小 XML 範例加測試覆蓋 before/after
- 若新功能會產生 XML 結構，最終仍應讓 `_check_well_formed()` 作為最後防線
- 若會影響 ZIP 內容，確認 `save()` 與 manifest 更新路徑是否完整

## 附錄：公開 API 速查

```python
from odttpl import (
    OdtTemplate,
    RichText,
    RichTextParagraph,
    R,
    RP,
    Listing,
    InlineImage,
    OdtSubdoc,
    StructuredBlock,
    NumberedListStyle,
    BulletListStyle,
    LevelSpec,
    BulletLevelSpec,
    LabelFollowedBy,
    StructuredBlockError,
    SB,
    NLS,
)
```

常用入口：

```python
tpl = OdtTemplate("template.odt")

variables = tpl.get_undeclared_variables()
subdoc = tpl.new_subdoc("chapter.odt")

tpl.render(
    {
        "name": "Alice",
        "title": RichText(tpl, "Important", bold=True),
        "content": RichTextParagraph(tpl, "Body"),
        "body": Listing("Line one\nLine two"),
        "logo": InlineImage(tpl, "logo.png", width="3cm"),
        "chapter": subdoc,
        "block": StructuredBlock(tpl),
    },
    autoescape=True,
)

tpl.save("output.odt")
```
