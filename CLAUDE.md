## 說明

這個專案資料夾是我請你參考 python-docx-template，並改寫為生成 odt 檔的 package

## 主要元件摘要

- 核心引擎 `odttpl/template.py` 的 `OdtTemplate`：負責 `patch_xml` → Jinja2 渲染 → 後處理 → 寫回 ZIP。
- 元素級 Jinja shorthand（由 `_TAG_MAP` 定義，`patch_xml` 會在渲染前把整個元素替換為純 Jinja tag）：
  - `{%tr` → `<table:table-row>`
  - `{%tc` → `<table:table-cell>`
  - `{%p` → `<text:p>`
  - `{%s` → `<text:span>`
  - `{%li` → `<text:list-item>`
- `_check_well_formed()`：在 `build_content_xml` / `build_styles_xml` 末尾以 `lxml.etree.fromstring` 驗證輸出 XML；若 Jinja tag 跨越 ODF 元素邊界，會拋出 `ValueError` 並在訊息中建議對應 shorthand。

## StructuredBlock 目前狀態

- `StructuredBlock` 已加入 `{{block VAR}}` shorthand：透過剝除外層 `<text:p>` 佔位符，插入混合的 `<text:p>` / `<text:list>` XML 片段。
- `StructuredBlock` 支援 `add_paragraph()`、`add_list_item()`、清單內延伸段落 `in_list_item=True`、`str` / `RichText` 內容，以及預設或自訂 list style。
- 清單樣式包含：
  - `NumberedListStyle` / `LevelSpec`
  - `BulletListStyle` / `BulletLevelSpec`
  - template 既有具名 list style 字串
- `OdtTemplate` 目前有三種 automatic style registry：
  - `_auto_styles`：RichText 字元樣式，產生 `odttpl_T{n}`
  - `_list_styles`：numbered / bullet list style，產生或引用 `odttpl_L{n}`
  - `_para_styles`：StructuredBlock 段落縮排樣式，產生 `odttpl_P{n}`
- `add_paragraph(margin_left=..., text_indent=...)` 會自動註冊 paragraph style；若指定 `parastyle`，則以既有樣式名為準。
- `render()` 每次會 reset text / list / paragraph style registry；`StructuredBlock._build()` 會重新註冊引用過的 list style，支援跨 render 重用。

## 測試重點

- `tests/test_structured_block.py` 涵蓋段落、巢狀清單、RichText、named / custom list style、`BulletListStyle`、paragraph indent、錯誤驗證，以及與 `{%li %}` 共存。
- 建議驗證指令：
  - `uv run pytest tests/test_structured_block.py -v`
  - `uv run pytest tests/ -v`
