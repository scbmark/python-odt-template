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
