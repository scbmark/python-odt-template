# odttpl 開發者指南

本文件說明 `odttpl` 套件的整體架構與設計思路，供後續維護參考。

---

## 目錄

1. [專案概述](#1-專案概述)
2. [目錄結構](#2-目錄結構)
3. [模組說明](#3-模組說明)
4. [核心資料流](#4-核心資料流)
5. [關鍵演算法](#5-關鍵演算法)
6. [狀態管理](#6-狀態管理)
7. [測試架構](#7-測試架構)
8. [擴充指引](#8-擴充指引)
9. [已知限制與 Trade-offs](#9-已知限制與-trade-offs)

---

## 1. 專案概述

**odttpl** 讓使用者以 LibreOffice 製作 `.odt` 範本，再透過 Jinja2 語法填入變數，產生最終文件。設計上參考 `python-docx-template` 的 API，但針對 ODF 格式重新實作。

**技術核心**：`.odt` 本質上是一個 ZIP 壓縮檔，內含多個 XML 檔案。本套件的工作就是：

```
讀取 ZIP → 修補 XML → Jinja2 渲染 → 後處理 → 寫回 ZIP
```

**依賴套件**：
- `jinja2`：範本渲染引擎
- `lxml`：XML 解析（用於樣式注入與 subdoc 合併）

---

## 2. 目錄結構

```
python-odt-template/
├── odttpl/
│   ├── __init__.py        # 公開 API 匯出
│   ├── template.py        # 核心引擎 OdtTemplate
│   ├── richtext.py        # 行內文字格式化
│   ├── listing.py         # 多行文字處理
│   ├── inline_image.py    # 圖片嵌入
│   └── subdoc.py          # 子文件合併
├── tests/
│   ├── test_template.py   # 功能測試
│   ├── make_templates.py  # 測試用 ODT 產生器
│   └── templates/         # 測試用 ODT 檔（由 make_templates.py 產生）
├── pyproject.toml
├── README.md / README.zh.md
└── CLAUDE.md
```

---

## 3. 模組說明

### 3.1 `template.py` — 核心引擎

**類別**：`OdtTemplate`

這是整個套件的主體，負責協調所有流程。

**重要屬性（`__init__` 初始化）**：

| 屬性 | 型別 | 用途 |
|------|------|------|
| `_template_data` | `bytes` | 原始 ZIP 的記憶體快取，支援多次渲染 |
| `_modified_files` | `dict[str, bytes]` | 渲染後被修改的 XML 檔案 |
| `_auto_styles` | `dict` | 自動樣式登錄表（key: props tuple → value: style 名稱） |
| `_extra_images` | `dict` | 需要寫入 ZIP 的額外圖片 |
| `_subdocs` | `list` | 本次渲染中用到的所有 OdtSubdoc |
| `_subdoc_counter` | `int` | 用來給 subdoc 分配唯一前綴 |

**重要方法**：

| 方法 | 說明 |
|------|------|
| `render(context, ...)` | 主流程入口，協調所有步驟 |
| `save(output)` | 將渲染結果寫出為 ZIP |
| `patch_xml(xml)` | 修補 LibreOffice 切碎 Jinja2 標籤的問題（見第 5 節） |
| `render_xml_part(xml, context)` | 執行 Jinja2 渲染並做後處理 |
| `resolve_listing(xml)` | 將 `\n\t\a\f` 展開為 ODF XML 元素 |
| `_merge_consecutive_lists(xml)` | 修正迴圈展開後產生的多餘 `<text:list>` |
| `_inject_auto_styles(xml)` | 將 RichText 樣式定義注入 XML |
| `_register_text_style(**props)` | 登錄一個文字樣式，回傳樣式名稱 |
| `_add_image(image)` | 將 InlineImage 登記至 `_extra_images` |
| `new_subdoc(path)` | 建立 OdtSubdoc 實例 |
| `get_undeclared_variables()` | 分析範本，回傳所有未宣告變數 |

---

### 3.2 `richtext.py` — 行內格式化

**類別**：`RichText`（別名 `R`）

用來在 Jinja2 context 中傳入帶有格式的文字片段。

**使用流程**：

```python
rt = RichText()
rt.add("粗體", bold=True)
rt.add(" 紅色", color="#FF0000")
context = {"title": rt}
```

**內部機制**：
- 呼叫 `add()` 時，只記錄文字與格式屬性，不產生 XML。
- Jinja2 渲染時呼叫 `__html__()`（autoescape 模式）或 `__str__()`，此時才呼叫 `_build()`。
- `_build()` 呼叫 `tpl._register_text_style(**props)` 取得樣式名稱，再產生 `<text:span style-name="...">` XML。
- 樣式定義由 `OdtTemplate._inject_auto_styles()` 在渲染後注入 content.xml。

**延遲建立的原因**：必須在每次 `render()` 重置後才能登錄樣式，確保 `_auto_styles` 是乾淨的。

---

**類別**：`RichTextParagraph`（別名 `RP`）

用來插入帶有段落樣式的文字，對應範本中的 `{{p variable }}` 語法。

```python
rp = RichTextParagraph("內容", style="Heading_20_1")
```

會產生 `<text:p text:style-name="Heading_20_1">內容</text:p>`。

---

### 3.3 `listing.py` — 多行文字

**類別**：`Listing`

解決 Jinja2 直接插入含換行符號的字串時，會被 XML escape 掉的問題。

```python
context = {"body": Listing("第一行\n第二行\t縮排\a新段落")}
```

**特殊字元對應**：

| 字元 | 意義 | 展開為 |
|------|------|--------|
| `\n` | 軟換行（同段落） | `<text:line-break/>` |
| `\t` | Tab | `<text:tab/>` |
| `\a` | 新段落 | 結束並開啟 `<text:p>` |
| `\f` | 分頁後新段落 | `<text:soft-page-break/>` + 新 `<text:p>` |

**處理時機**：`Listing.__html__()` 只做 HTML escape（保留特殊字元），Jinja2 渲染完成後，`resolve_listing()` 再用 regex 展開。

---

### 3.4 `inline_image.py` — 圖片嵌入

**類別**：`InlineImage`

```python
img = InlineImage(tpl, "photo.png", width=Cm(5))
context = {"photo": img}
```

**內部機制**：
- Jinja2 渲染時呼叫 `_build_xml()`，產生 `<draw:frame><draw:image .../></draw:frame>` XML。
- 同時呼叫 `tpl._add_image(self)` 將圖片記錄到 `_extra_images`。
- `save()` 時將圖片位元組寫入 ZIP 的 `Pictures/` 目錄。
- `_update_manifest()` 在 `META-INF/manifest.xml` 新增對應紀錄。
- 圖片以 MD5 hash 作為檔名，避免重複。

---

### 3.5 `subdoc.py` — 子文件合併

**類別**：`OdtSubdoc`

允許將另一個 `.odt` 檔案的內容嵌入主文件。

```python
subdoc = tpl.new_subdoc("chapter1.odt")
context = {"chapter": subdoc}
```

**核心挑戰**：不同文件可能有相同名稱的自動樣式（如 `T1`、`P1`），直接合併會衝突。

**解決方案**：以唯一前綴重命名所有樣式與圖片。

**處理流程**：
1. `OdtSubdoc.__init__()` — 讀取並解析 `.odt` ZIP，提取 body XML、自動樣式、圖片。
2. `_reset()` — 每次 `render()` 開始時清空上次的狀態，讓同一個 subdoc 可以多次使用。
3. `_ensure_renamed()` — 首次呼叫時分配計數器（`odttpl_sd1_`、`odttpl_sd2_`...），用正則替換所有樣式名稱和圖片路徑。
4. `_get_xml()` — 回傳已重命名的 body XML（供 Jinja2 渲染時插入）。
5. 渲染完成後，`OdtTemplate` 收集所有 subdoc 的樣式，注入主文件的 `<office:automatic-styles>`。

---

## 4. 核心資料流

以下展示一次完整的 `render()` + `save()` 的執行路徑：

```
render(context)
│
├─ [重置階段]
│   ├─ 清空 _modified_files, _auto_styles, _extra_images
│   └─ 對 context 中所有 OdtSubdoc 呼叫 _reset()
│
├─ [建構 content.xml]
│   ├─ 從 _template_data 取出原始 content.xml
│   ├─ patch_xml() ──────────────────────────── 修補 XML（共 6 步）
│   ├─ Jinja2 Template(xml).render(context)
│   │   └─ 過程中呼叫各 context 物件的 __str__ / __html__：
│   │       ├─ RichText → _build() → 登錄樣式 + 回傳 <text:span>
│   │       ├─ Listing → escape 後回傳（含 \n 等特殊字元）
│   │       ├─ InlineImage → _build_xml() → 登錄圖片 + 回傳 <draw:frame>
│   │       └─ OdtSubdoc → _get_xml() → 回傳已重命名的 body XML
│   ├─ resolve_listing() ──────────────────────── 展開 \n \t \a \f
│   └─ _merge_consecutive_lists() ───────────── 修正迴圈後的 <text:list>
│
├─ [樣式注入]
│   └─ _inject_auto_styles() ─────────────────── 將 RichText 樣式定義插入 XML
│
├─ [合併 subdoc 資源]
│   └─ 對每個 OdtSubdoc：
│       ├─ 將其自動樣式 XML 注入 content.xml
│       └─ 將其圖片加入 _extra_images
│
├─ [建構 styles.xml]（流程同上，錯誤會被忽略）
│
└─ _update_manifest() ───────────────────────── 更新 manifest.xml

save(output)
│
├─ 開啟原始 _template_data 為 ZIP 讀取
├─ 建立新 ZIP 輸出
├─ 複製所有原始檔案，跳過 _modified_files 中的
├─ 寫入 _modified_files 中的修改檔案
└─ 將 _extra_images 的圖片寫入 Pictures/
```

---

## 5. 關鍵演算法

### 5.1 `patch_xml()` — XML 修補

**問題根源**：LibreOffice 在儲存含有 Jinja2 語法的文件時，會將標籤切碎。例如：

```xml
<!-- 原本寫的 -->
{{ name }}

<!-- LibreOffice 儲存後變成 -->
<text:span text:style-name="T1">{</text:span><text:span>{</text:span> name <text:span>}</text:span><text:span>}</text:span>
```

**六步修補流程**：

| 步驟 | 說明 |
|------|------|
| 1 | 移除緊鄰 `{{`、`{%`、`}}`、`%}` 的多餘標籤 |
| 2 | 移除 Jinja2 區塊**內部**的 span 邊界標籤 |
| 3 | 處理 `{%tr`、`{%p`、`{%s` 等縮寫，從所在元素中提取出來 |
| 4 | 處理 `{%-`、`-%}` 空白修剪語法 |
| 5 | 追蹤 span 巢狀深度，丟棄孤立的 `</text:span>` |
| 6 | 反轉義標籤內的 HTML 實體（`&amp;` → `&` 等） |

**設計考量**：使用正則而非完整 XML 解析，速度較快，且能應對 LibreOffice 產生的非標準格式。

---

### 5.2 `_merge_consecutive_lists()` — 修正迴圈中的清單

**問題**：Jinja2 的 `{% for %}` 迴圈展開後，每次迭代各自包一個 `<text:list>`，導致自動編號重置：

```xml
<!-- 展開後 -->
<text:list><text:list-item>1. 項目 A</text:list-item></text:list>
<text:list><text:list-item>1. 項目 B</text:list-item></text:list>  ← 又從 1 開始
```

**解法**：狀態機式的 token 掃描，將相鄰且樣式相同的 `<text:list>` 合併。

```xml
<!-- 合併後 -->
<text:list>
  <text:list-item>1. 項目 A</text:list-item>
  <text:list-item>2. 項目 B</text:list-item>
</text:list>
```

**注意**：只合併最外層的 list；巢狀 list 不受影響。

---

### 5.3 自動樣式登錄（Registry Pattern）

`RichText` 使用的格式屬性會以 tuple 作為 key 進行去重：

```python
# _auto_styles: dict[tuple, str]
# key: (("bold", True), ("color", "#FF0000"))
# value: "odttpl_T1"
```

相同格式只會產生一個樣式定義，節省檔案大小。

---

## 6. 狀態管理

`OdtTemplate` 的多次 `render()` 能力倚賴嚴格的狀態重置：

```python
def render(self, context, ...):
    # 每次 render 開始時重置所有可變狀態
    self._modified_files = {}
    self._auto_styles = {}
    self._extra_images = {}
    self._subdocs = []
    self._subdoc_counter = 0
    # ...
```

`_template_data`（原始 ZIP bytes）**永遠不被修改**，確保可以重複渲染。

`OdtSubdoc` 也有自己的 `_reset()`，在每次渲染開始時清除前一次的樣式重命名狀態。

---

## 7. 測試架構

### 測試環境建立

測試用的 `.odt` 範本由 `make_templates.py` 程式化產生，不需要 LibreOffice。

```bash
cd tests
python make_templates.py   # 產生 templates/*.odt
pytest test_template.py
```

### 測試分類

| 測試 | 涵蓋功能 |
|------|---------|
| `test_simple_variable` | 基本變數替換 |
| `test_variable_escaped` | autoescape 防 XML injection |
| `test_loop_table` | `{%tr for ...` 表格列迴圈 |
| `test_listing_*` | Listing 換行、Tab 展開 |
| `test_richtext_*` | 粗體、顏色、具名樣式 |
| `test_conditional_*` | `{%p if ...` 段落條件 |
| `test_undeclared_variables` | 變數分析 API |
| `test_save_to_file` | 儲存至路徑（非 BytesIO）|
| `test_multi_render` | 同一個 template 物件多次渲染 |
| `test_subdoc_*` | subdoc 插入、樣式合併、多次渲染 |

### 測試輔助模式

```python
# 調試時可輸出 XML 觀察渲染結果
tpl.render(context)
print(tpl._modified_files.get("content.xml", b"").decode())
```

---

## 8. 擴充指引

### 新增一種 Context 物件類型

若要支援新的物件（例如超連結、表格等），需要實作以下介面：

```python
class MyObject:
    def __html__(self):
        # autoescape=True 時使用
        return markupsafe.Markup("<text:a ...>...</text:a>")

    def __str__(self):
        # autoescape=False 時使用
        return "<text:a ...>...</text:a>"
```

若需要在 `save()` 時寫入額外資源（如圖片），在 `__html__` / `__str__` 中呼叫 `tpl._add_image()` 或自行擴充 `OdtTemplate`。

### 新增 patch_xml 步驟

`patch_xml()` 使用序列 regex 替換，新增步驟時只需在對應位置加入：

```python
def patch_xml(self, xml: str) -> str:
    # 現有步驟 1-6...

    # 新增步驟 7：處理某種新的 LibreOffice 奇怪行為
    xml = re.sub(r"<某個pattern>", r"替換內容", xml)

    return xml
```

**建議**：每個步驟加上注解說明要解決的問題，並附上範例 XML before/after。

### 支援新的 ODF 元素

ODF 規格複雜，新增支援時建議：
1. 在 LibreOffice 建立一個含目標格式的 `.odt` 檔
2. 解壓 ZIP，觀察 `content.xml` 的 XML 結構
3. 確認對應的 ODF XML 規格

---

## 9. 已知限制與 Trade-offs

| 限制 | 原因 | 可能的改善方向 |
|------|------|---------------|
| `patch_xml()` 用正則處理 XML | 效能優先，且 LibreOffice 輸出格式尚算固定 | 遇到新的 edge case 需新增 regex 步驟 |
| 整個 ZIP 載入記憶體 | 支援多次渲染 | 超大文件（>100MB）不適用 |
| Subdoc 中無法使用 Jinja2 | 合併時是直接插入 XML，不再渲染 | 若需要，需在 `_get_xml()` 前先渲染 subdoc |
| 樣式需手動在 LibreOffice 中定義 | RichText 的「具名樣式」引用的是範本中已存在的樣式 | 可考慮允許程式化定義段落樣式 |
| `styles.xml` 渲染錯誤會被靜默忽略 | 避免範本中 styles.xml 沒有 Jinja2 內容時拋出錯誤 | 若未來 styles.xml 變數化，需調整此行為 |

---

## 附錄：公開 API 速查

```python
from odttpl import OdtTemplate, RichText, R, RichTextParagraph, RP, Listing, InlineImage

tpl = OdtTemplate("template.odt")

# 取得所有需要的變數名稱
vars = tpl.get_undeclared_variables()

# 渲染
tpl.render({
    "name": "世界",
    "title": RichText("標題", bold=True, color="#0000FF"),
    "body": Listing("第一行\n第二行"),
    "photo": InlineImage(tpl, "img.png", width=Cm(5)),
    "chapter": tpl.new_subdoc("chapter.odt"),
    "items": [{"name": "A"}, {"name": "B"}],
})

# 儲存
tpl.save("output.odt")

# 或存至記憶體
import io
buf = io.BytesIO()
tpl.save(buf)
```

---

*本指南對應版本：v0.1.0*
