# StructuredBlock 開發計畫

> 本文件供任何接手者（包括未來的 AI agent）順利接續此功能開發。
> 完整設計脈絡請參考 [new_plan.md](new_plan.md)。

---

## 為什麼做這個功能

`python-odt-template` 目前在生成「混合普通段落 + 多層編號清單 + 清單內補充段落」這類複雜文件時，需要為不同情境維護多份 `.odt` 模板（模板爆炸），且 Jinja 語法在 ODF XML 中難以表達複雜邏輯。

**StructuredBlock** 是一組高階 Python builder：使用者在 Python 端宣告完整段落／清單結構，由 renderer 一次產出乾淨的 ODF XML 片段，再透過新增的 `{{block ...}}` shorthand 插入模板。與既有 `RichText` / `RichTextParagraph` / `{%li %}` 共存，不破壞舊有 API。

---

## 已確認的設計決策

1. **List style 雙軌**：可引用模板既有命名 list-style，也可在 Python 中以 `NumberedListStyle` 程式化定義並自動註冊到 `<office:automatic-styles>`。未指定時自動註冊一個 1./1.1/1.1.1 多層編號預設樣式。
2. **`text` 欄位**：接受 `str` 或 `RichText`；RichText 走既有 `_build()` 路徑自動註冊字元樣式。
3. **新增 `{{block VAR}}` shorthand**：在 `_TAG_MAP` 加入 `("block", "text:p")`，剝除 placeholder `<text:p>` 後置入混合 XML。
4. **嚴格驗證**：level 跳級、`in_list_item=True` 但無開啟清單、level<1 一律拋 `StructuredBlockError`。
5. **與 `{%li %}` 並存**，互不影響。
6. **預設清單樣式**：5 層多層編號（1./1.1./...）。
7. **Renderer 採字串組裝**（非 lxml），與現有 `RichText` 一致，由 `_check_well_formed` 在 render 末段驗證整份 XML。

---

## 開發階段

開發分三階段。每階段結束時應 commit，方便對照與回溯。

---

### Phase 1（核心）— ✅ 已完成

最小可運作骨架：能在程式中組出 paragraph + 巢狀清單，渲染為合法 ODF XML 並插入模板。

#### 已交付

- ✅ 新增 `odttpl/structured_block.py`：
  - `StructuredBlockError(ValueError)` 例外。
  - `LevelSpec` dataclass（多層編號定義）。
  - `NumberedListStyle` — 程式化定義 list-style，自動註冊到 `tpl._list_styles`。
  - `ParagraphNode` / `ListItemNode` / `_ListGroup` AST 節點。
  - `StructuredBlock` builder：`add_paragraph`、`add_list_item`、`close_list`、`__str__` / `__html__`。
  - `_render_inline(text)` helper 統一處理 `str` / `RichText`。
  - `_referenced_styles` 追蹤所有用過的 NumberedListStyle，於 `_build()` 重新註冊以對抗 render reset。
- ✅ 修改 `odttpl/template.py`：
  - `_TAG_MAP` 加入 `("block", "text:p")`。
  - `__init__` 新增 `self._list_styles: dict[str, Any] = {}`。
  - `render()` reset 區同步清空 `_list_styles`。
  - 新增 `_next_list_style_name()`、`_register_list_style(style)`、`_build_list_styles_xml()`。
  - `_inject_auto_styles` 同時注入 list-style XML；render 注入條件改為 `if self._auto_styles or self._list_styles`。
  - **bug 修正**：`_inject_auto_styles` 改用 `re.subn` 偵測 self-closing 是否被替換；先前邏輯會在 self-closing form 同時觸發 re.sub 與後續 .replace，導致樣式被注入兩次。
- ✅ 更新 `odttpl/__init__.py` 匯出 `StructuredBlock`、`NumberedListStyle`、`LevelSpec`、`StructuredBlockError`、別名 `SB` / `NLS`。
- ✅ 跑既有 `pytest tests/`：25 passed。
- ✅ 端到端煙霧測試覆蓋：混合段落+清單、巢狀清單於 list-item 內、continuation paragraph、`RichText` 內嵌、自訂 NumberedListStyle、跨 render 重用、嚴格驗證例外。

#### 與原計畫的差異

- 移除了 `tpl._default_block_list_style_name` 跨 block 共享的設計。改由每個 `StructuredBlock` 自己持有 `_default_style_obj`。原因：`OdtTemplate.render()` 會清空所有 per-render 狀態；改用 per-block 引用追蹤+`_build()` 重新註冊，比 tpl-level 快取更穩健。實際上若兩個 block 都使用各自的預設，會註冊出 `odttpl_L1` 與 `odttpl_L2` 兩份相同樣式定義（無功能影響，僅多幾百 bytes）。Phase 3 可再優化。

#### 不在 Phase 1 範圍

- `BulletListStyle`（項目符號樣式）。
- `_register_para_style` 與 `ParagraphNode.margin_left` / `text_indent` 實際生效（API 先保留簽名但不註冊樣式）。
- 新 fixture 模板與 18 個 pytest 測試。
- README 章節。

#### 驗收

```bash
uv run pytest tests/                       # 既有測試全綠
uv run python -c "from odttpl import StructuredBlock, NumberedListStyle, LevelSpec; print('ok')"
```

---

### Phase 2（測試 + fixture）

把 `StructuredBlock` 用真實渲染流程驗證。

#### 範圍

- [ ] `tests/make_templates.py` 新增 fixture 產生器：
  - `structured_block.odt` — body 含 `<text:p>Header</text:p><text:p>{{block content}}</text:p><text:p>Footer</text:p>`。
  - `structured_block_in_cell.odt` — `<table:table-cell><text:p>{{block content}}</text:p></table:table-cell>`。
  - `structured_block_with_li.odt` — 同模板含 `{{block ...}}` 與 `{%li for x in xs %}` 兩種寫法。
- [ ] `tests/test_structured_block.py` 完整 18 個案例（清單見下）。

#### 測試清單

採用 [test_template.py](tests/test_template.py) 的 `_render` 與 `_content_xml` helper。

1. `test_simple_paragraph_only` — 單一段落、無 list。
2. `test_paragraph_then_list_then_paragraph` — 順序與 list 自動關閉。
3. `test_three_level_nested_numbered_list` — 巢狀 `<text:list>` 位於 `<text:list-item>` 內、非兄弟。
4. `test_list_item_with_continuation_paragraphs` — `in_list_item=True` 同 `<text:list-item>` 內出現兩 `<text:p>`。
5. `test_richtext_inside_list_item` — `RichText` 字元樣式被註冊。
6. `test_richtext_inside_paragraph` — 同上對段落。
7. `test_level_skip_raises` — 1→3 拋 `StructuredBlockError`。
8. `test_in_list_item_without_open_list_raises` — 拋。
9. `test_invalid_level_raises` — `level=0` 拋。
10. `test_default_list_style_auto_registered` — `odttpl_L1` 同時出現於 `<text:list>` 與 `<office:automatic-styles>`。
11. `test_named_template_list_style_used_verbatim` — 不額外註冊。
12. `test_numbered_list_style_custom_levels` — `format="A"` / `suffix=")"` 等出現於 XML。
13. `test_well_formed_after_render` — 複雜混合情境通過 `_check_well_formed`。
14. `test_consecutive_blocks_share_default_style` — 只註冊一份。
15. `test_block_coexists_with_li_shorthand` — 同模板兩種共存。
16. `test_list_then_unrelated_paragraph_closes_list`。
17. `test_paragraph_margin_left_creates_para_style` — Phase 3 才會通過，先 skip 或留 TODO。
18. `test_block_inside_table_cell` — `<table:table-cell>` 內 placeholder 正常剝除。

#### 驗收

```bash
uv run python tests/make_templates.py
uv run pytest tests/test_structured_block.py -v
uv run pytest tests/ -v
```

---

### Phase 3（擴充與文件）

#### 範圍

- [ ] `BulletListStyle` 與預設 bullet 樣式選項。
- [ ] `_register_para_style(**props)` 與 `_build_para_styles_xml()`，讓 `ParagraphNode.margin_left` / `text_indent` 真正生效。
- [ ] `ParagraphNode.list_continue=True` 等選項（如有需求）。
- [ ] `README.md` 新增 `## StructuredBlock` 章節：
  - 基本範例（混合段落 + 兩層清單）。
  - 自訂 `NumberedListStyle` 範例。
  - 與 `{%li %}` 共存說明。
- [ ] 視需求更新 `DEVELOPER_GUIDE.md`。

---

## 關鍵檔案參考

- 整合點：[odttpl/template.py](odttpl/template.py)
  - `_TAG_MAP`：第 180–186 行。
  - `_register_text_style` / `_build_auto_styles_xml` / `_inject_auto_styles`：第 636–714 行（新增 list-style 函式時請就近並列）。
  - `render()` reset 區：約 796–800 行。
  - `_check_well_formed`：第 605–630 行（不需修改）。
- 對照範本：[odttpl/richtext.py](odttpl/richtext.py)
  - `RichText._build()`（第 149–164 行）示範 lazy 樣式註冊。
- 既有測試模式：[tests/test_template.py](tests/test_template.py) + [tests/make_templates.py](tests/make_templates.py)。

---

## 注意事項

1. **跨 block 編號**：Renderer 會在每個頂層 `<text:list>` 加 `text:continue-numbering="false"`，避免 `_merge_consecutive_lists` 之後與其他清單意外延續。如要連續編號需另開參數。
2. **預設 list style 縮排**：採 inline `style:list-level-label-alignment`（非引用 `Numbering_20_Symbols`），免除模板 dependency。
3. **Inline 跳脫**：`str` 用 `html.escape`；`RichText` 已預跳脫，呼叫 `text._build()` 直接內嵌。集中於 `_render_inline` helper。
4. **重複 render**：`render()` reset 階段會清空所有自動樣式註冊；同一個 `StructuredBlock` 跨 render 重用時，`__str__` 會在新 render 中重新註冊。
5. **lxml 不必要**：renderer 用字串組裝即可，最終由 `_check_well_formed` 對整份 content.xml 呼叫 `etree.fromstring` 把關。
