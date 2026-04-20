# StructuredBlock 設計說明（ODT 動態區塊生成架構）

## 一、背景與需求

目前 `python-odt-template` 的主要設計模式是：

- 使用 Jinja-like 語法在 `.odt` 模板中標記變數
- 由 Python 端傳入資料進行替換
- 已支援：
  - `{{p ...}}`：段落級替換
  - `RichText`：inline rich text
  - `RichTextParagraph`：多段 paragraph
  - `{%li ... %}`：清單項目 loop

---

### 現有問題

在實際文件生成中，遇到以下困境：

1. **文件某些區塊結構複雜**
   - 混合：
     - 普通段落
     - 多層編號清單
     - 清單內補充段落

   - 且排列規則取決於程式邏輯（非靜態模板）

2. **模板爆炸問題**
   - 為不同情境建立多份 `.odt` 模板
   - 維護成本高
   - 難以擴充

3. **模板語法不適合處理複雜邏輯**
   - Jinja 在 ODT XML 中容易破壞結構
   - `{%li %}` 雖可解部分問題，但仍不適合複雜判斷

---

## 二、目標

設計一個機制，使：

> **所有邏輯在 Python 中完成，模板只負責插入結果**

具體目標：

- Python 控制：
  - 每一行內容
  - 是否為清單項目
  - 清單層級
  - 縮排與樣式

- 支援：
  - 多層清單
  - 清單內段落
  - RichText

- 輸出：
  - 正確的 ODF XML（非純文字假編號）

---

## 三、設計核心概念

### 1. StructuredBlock

一個高階物件：

- 用來在 Python 中構建「文件片段」
- 最終輸出為 ODF XML
- 可直接插入模板：

```jinja2
{{p section }}
```

---

### 2. 設計原則

#### 原則 1：資料與呈現分離

- Python：描述「結構」
- Renderer：轉成 ODF XML

---

#### 原則 2：避免模板邏輯

- 不在模板中做：
  - if / loop / 判斷

- 模板只負責「插入」

---

#### 原則 3：以 ODF 結構為核心

支援：

- `<text:p>`
- `<text:list>`
- `<text:list-item>`

---

#### 原則 4：與既有 API 一致

- 風格類似：
  - `RichText`
  - `RichTextParagraph`

---

## 四、系統架構

```
StructuredBlock (API)
        ↓
BlockNodes (AST)
        ↓
OdfBlockRenderer
        ↓
ODF XML
        ↓
{{p ...}} 插入模板
```

---

## 五、資料模型（AST）

### 1. ParagraphNode

```python
ParagraphNode:
    text
    parastyle
    margin_left
    text_indent
```

---

### 2. ListItemNode

```python
ListItemNode:
    text
    level
    list_style
    parastyle
    body (list[ParagraphNode])
    children (list[ListItemNode])
```

---

### 3. DocumentFragment

```python
DocumentFragment:
    children: list[BlockNode]
```

---

## 六、Builder 設計（StructuredBlock）

### 核心能力

```python
block = StructuredBlock(tpl)

block.add_paragraph(...)
block.add_list_item(...)
```

---

### 關鍵設計：List Stack

內部維護：

```python
self._list_stack
```

用途：

- 根據 `level` 自動建立巢狀結構
- 管理當前清單上下文

---

### 行為規則

#### 1. 新增段落

- `in_list_item=True`
  → 加入當前 list item

- 否則：
  → 加入 root

---

#### 2. 新增 list item

- 根據 `level`：
  - 調整 stack
  - 建立巢狀結構

---

#### 3. 關閉 list

```python
_close_list_context()
```

---

## 七、Renderer 設計

### 職責

將 AST → ODF XML

---

### 核心邏輯

#### 1. Paragraph → `<text:p>`

#### 2. List grouping

連續 ListItemNode：

```text
ListItemNode
ListItemNode
ListItemNode
```

→ 合併為一個 `<text:list>`

---

#### 3. 巢狀 list

```xml
<text:list>
  <text:list-item>
    <text:p>...</text:p>

    <text:list>
      ...
    </text:list>

  </text:list-item>
</text:list>
```

---

## 八、解決的問題

### ✔ 解決

1. 模板爆炸
2. 複雜邏輯無法用 Jinja 表達
3. 清單巢狀難以維護
4. ODT XML 容易被破壞
5. 文件結構與程式邏輯分離

---

## 九、限制（v1）

### 限制 1：樣式需預先定義

- `parastyle`
- `list_style`

需在 ODT 模板中存在

---

### 限制 2：level 不可跳級

```text
1 → 3 ❌
1 → 2 → 3 ✔
```

---

### 限制 3：需明確控制 in_list_item

錯誤使用會丟 exception

---

### 限制 4：不保證自動續號

- start_value / continue_numbering
- 可在 v2 實作

---

### 限制 5：不支援複雜 style 動態生成（v1）

---

## 十、未來擴充方向

### v2

- 自動 paragraph style 註冊
- 動態縮排
- keep-with-next

---

### v3

- 高階 DSL

```python
block.add_clause(...)
block.add_subclause(...)
```

---

### v4

- 多輸出格式（HTML / DOCX）

---

## 十一、風險與注意事項

### 1. ODF XML 結構嚴格

- tag 必須正確巢狀
- namespace 正確

---

### 2. List 結構複雜

- `<text:list>` 與 `<text:list-item>` 層級需正確

---

### 3. LibreOffice 行為依賴 style

- style 設計不良會影響排版

---

### 4. 不建議手寫 XML

應使用：

- `lxml`
- 或 odfpy node API

---

## 十二、結論

此設計將：

> **python-odt-template 從「模板替換工具」提升為「結構化文件生成引擎」**

核心價值：

- 減少模板數量
- 提高可維護性
- 提升彈性
- 適合複雜文件生成（報告 / 法規 / 稽核）

---

## 十三、下一步

實作 Phase 1：

- `StructuredBlock`
- `BlockNodes`
- `OdfBlockRenderer`

並完成：

- paragraph + list 基本功能
- 多層清單
- list 內段落

---
