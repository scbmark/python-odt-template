# ODT 與 DOCX 底層格式指南

本文件說明 `.odt`（OpenDocument Text）與 `.docx`（Office Open XML）兩種文件格式的底層結構，包含解壓後的檔案組成，以及各 XML 的內容規範。

---

## 目錄

1. [共同概念：兩者都是 ZIP](#1-共同概念兩者都是-zip)
2. [ODT 格式（ODF 規範）](#2-odt-格式odf-規範)
3. [DOCX 格式（OOXML 規範）](#3-docx-格式ooxml-規範)
4. [兩種格式對照比較](#4-兩種格式對照比較)
5. [XML 命名空間速查](#5-xml-命名空間速查)

---

## 1. 共同概念：兩者都是 ZIP

`.odt` 和 `.docx` 本質上都是 **ZIP 壓縮檔**，將多個 XML 與資源檔打包在一起。你可以直接用任何 ZIP 工具解壓縮。

```bash
# Linux / macOS
unzip document.odt -d odt_contents/
unzip document.docx -d docx_contents/

# Python
import zipfile
with zipfile.ZipFile("document.odt") as z:
    z.extractall("odt_contents/")
```

兩者的關鍵差異在於：選用的 XML 規範不同、設計哲學不同。

---

## 2. ODT 格式（ODF 規範）

**規範全名**：OASIS Open Document Format for Office Applications（ODF）
**目前版本**：ODF 1.3（向下相容 1.2）
**制定組織**：OASIS（開放標準組織），非微軟主導
**主要應用**：LibreOffice、OpenOffice

### 2.1 解壓後的檔案結構

一個典型的 `.odt` 解壓後如下：

```
document.odt（解壓後）
│
├── mimetype                    ← 必須是第一個檔案，且不壓縮
├── META-INF/
│   └── manifest.xml            ← 目錄清單（列出所有檔案及 MIME 類型）
├── content.xml                 ← 文件本文（最重要）
├── styles.xml                  ← 具名樣式定義
├── meta.xml                    ← 文件屬性（作者、建立時間等）
├── settings.xml                ← LibreOffice 視窗設定（捲軸位置等）
├── Thumbnails/
│   └── thumbnail.png           ← 預覽縮圖
└── Pictures/
    ├── image1.png              ← 嵌入的圖片（有時才有）
    └── image2.jpg
```

> 最小合法的 `.odt` 只需要：`mimetype` + `META-INF/manifest.xml` + `content.xml`（styles.xml 建議一起附上）。本專案的測試範本就是這樣構成的。

---

### 2.2 `mimetype`

**作用**：宣告這個 ZIP 是什麼類型的文件。
**格式要求**：純文字，**無 BOM、無換行**，且必須是 ZIP 的**第一個 entry**，且使用 `ZIP_STORED`（不壓縮）。

```
application/vnd.oasis.opendocument.text
```

其他 ODF 類型（同樣使用 ZIP，只是 mimetype 不同）：

| MIME Type | 對應格式 |
|-----------|---------|
| `application/vnd.oasis.opendocument.text` | `.odt` 文字文件 |
| `application/vnd.oasis.opendocument.spreadsheet` | `.ods` 試算表 |
| `application/vnd.oasis.opendocument.presentation` | `.odp` 簡報 |
| `application/vnd.oasis.opendocument.graphics` | `.odg` 繪圖 |

---

### 2.3 `META-INF/manifest.xml`

**作用**：列出這個 ZIP 包含的所有有意義的檔案及其 MIME 類型，類似目錄索引。若有嵌入圖片，也要在這裡登記，否則 LibreOffice 不會讀取。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest
    xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
    manifest:version="1.2">

  <!-- 根目錄 → 宣告整個文件的類型 -->
  <manifest:file-entry
      manifest:full-path="/"
      manifest:version="1.2"
      manifest:media-type="application/vnd.oasis.opendocument.text"/>

  <!-- 各 XML 檔案 -->
  <manifest:file-entry manifest:full-path="content.xml"
      manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml"
      manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="meta.xml"
      manifest:media-type="text/xml"/>

  <!-- 嵌入圖片 -->
  <manifest:file-entry manifest:full-path="Pictures/photo.png"
      manifest:media-type="image/png"/>
</manifest:manifest>
```

---

### 2.4 `content.xml` — 文件本文（最核心）

**作用**：存放文件的實際內容（段落、表格、圖片位置等），以及僅供這個文件使用的「自動樣式」。

#### 整體骨架

```xml
<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
    xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
    office:version="1.2">

  <!-- 區塊 1：自動樣式（程式產生的一次性樣式） -->
  <office:automatic-styles>
    <style:style style:name="T1" style:family="text">
      <style:text-properties fo:font-weight="bold"/>
    </style:style>
  </office:automatic-styles>

  <!-- 區塊 2：文件本文 -->
  <office:body>
    <office:text>
      <!-- 實際內容在這裡 -->
    </office:text>
  </office:body>

</office:document-content>
```

#### 段落 `<text:p>`

```xml
<!-- 無樣式的段落 -->
<text:p>這是一段普通文字。</text:p>

<!-- 套用具名樣式的段落 -->
<text:p text:style-name="Heading_20_1">這是標題一</text:p>

<!-- 段落內的行內格式化：用 text:span 包裹 -->
<text:p text:style-name="Default">
  普通文字，
  <text:span text:style-name="T1">這段是粗體</text:span>，
  繼續普通文字。
</text:p>
```

> **樣式名稱的空格規則**：LibreOffice 中的樣式名「Heading 1」在 XML 裡必須寫成 `Heading_20_1`（空格編碼為 `_20_`，因為 XML attribute 不能含空格）。

#### 表格 `<table:table>`

```xml
<table:table table:name="MyTable">
  <table:table-column/>          <!-- 欄定義，每欄一個 -->
  <table:table-column/>
  <table:table-row>              <!-- 列 -->
    <table:table-cell>           <!-- 儲存格 -->
      <text:p>Row 1, Col 1</text:p>
    </table:table-cell>
    <table:table-cell>
      <text:p>Row 1, Col 2</text:p>
    </table:table-cell>
  </table:table-row>
</table:table>
```

#### 圖片 `<draw:frame>`

```xml
<draw:frame
    draw:style-name="fr1"
    draw:name="Image1"
    text:anchor-type="as-char"
    svg:width="5cm"
    svg:height="3cm">
  <draw:image xlink:href="Pictures/photo.png" xlink:type="simple" xlink:show="embed"/>
</draw:frame>
```

`text:anchor-type` 決定圖片錨定方式：
- `as-char`：行內圖片（與文字同行）
- `paragraph`：錨定在段落
- `page`：錨定在頁面（浮動）

#### 自動樣式 vs. 具名樣式的差異

| | 自動樣式（`office:automatic-styles`） | 具名樣式（`styles.xml` 的 `office:styles`） |
|---|---|---|
| 位置 | `content.xml` 或 `styles.xml` 的 `automatic-styles` 區塊 | `styles.xml` 的 `office:styles` |
| 用途 | 程式或 LibreOffice 自動產生，對應 UI 的「直接格式化」 | 使用者命名的樣式，對應「樣式」面板 |
| 名稱格式 | `T1`、`T2`、`P1`... | `Heading 1`、`Default`... |
| 可被繼承 | 不可 | 可（`style:parent-style-name`） |

---

#### 換行與特殊字元

```xml
<text:p>
  第一行
  <text:line-break/>    ← 軟換行（Shift+Enter），不開新段落
  第二行
  <text:tab/>           ← Tab 字元
  縮排後的文字
</text:p>
```

#### 清單 `<text:list>`

```xml
<text:list text:style-name="List_20_Bullet">
  <text:list-item>
    <text:p>項目 A</text:p>
  </text:list-item>
  <text:list-item>
    <text:p>項目 B</text:p>
  </text:list-item>
</text:list>
```

---

### 2.5 `styles.xml` — 樣式定義

**作用**：存放使用者在 LibreOffice「樣式」面板中建立的具名樣式，以及頁面佈局（page layout）、頁首頁尾（header/footer）等。

```xml
<office:document-styles ...>

  <!-- 具名樣式定義 -->
  <office:styles>
    <style:style style:name="Default" style:family="paragraph">
      <style:text-properties fo:font-size="12pt" fo:font-family="Times New Roman"/>
    </style:style>
    <style:style style:name="Heading_20_1" style:family="paragraph"
        style:parent-style-name="Default">
      <style:text-properties fo:font-size="18pt" fo:font-weight="bold"/>
    </style:style>
  </office:styles>

  <!-- 自動樣式（頁面版面等） -->
  <office:automatic-styles>
    <style:page-layout style:name="pm1">
      <style:page-layout-properties
          fo:page-width="21cm" fo:page-height="29.7cm"
          fo:margin-top="2.5cm" fo:margin-bottom="2cm"
          fo:margin-left="3cm" fo:margin-right="2cm"/>
    </style:page-layout>
  </office:automatic-styles>

  <!-- 主版面：指定頁面用哪個版面設定 -->
  <office:master-styles>
    <style:master-page style:name="Standard" style:page-layout-name="pm1">
      <style:header>
        <text:p>頁首文字</text:p>
      </style:header>
      <style:footer>
        <text:p>第 <text:page-number/>頁</text:p>
      </style:footer>
    </style:master-page>
  </office:master-styles>

</office:document-styles>
```

---

### 2.6 `meta.xml` — 文件屬性

```xml
<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta ...>
  <office:meta>
    <meta:creation-date>2024-01-01T00:00:00</meta:creation-date>
    <dc:creator>作者名稱</dc:creator>
    <dc:title>文件標題</dc:title>
    <meta:editing-duration>PT5M30S</meta:editing-duration>  <!-- ISO 8601 duration -->
    <meta:word-count>1234</meta:word-count>
  </office:meta>
</office:document-meta>
```

---

## 3. DOCX 格式（OOXML 規範）

**規範全名**：Office Open XML（OOXML / ECMA-376）
**目前版本**：ISO/IEC 29500
**制定組織**：微軟主導，後由 ECMA 及 ISO 標準化
**主要應用**：Microsoft Word

### 3.1 解壓後的檔案結構

```
document.docx（解壓後）
│
├── [Content_Types].xml             ← 所有檔案的 MIME 類型聲明（類似 ODT 的 manifest.xml）
├── _rels/
│   └── .rels                       ← 根層級關係檔案（指向 word/document.xml）
├── word/
│   ├── document.xml                ← 文件本文（最重要）
│   ├── styles.xml                  ← 樣式定義
│   ├── settings.xml                ← 文件設定
│   ├── theme/
│   │   └── theme1.xml              ← 色彩、字型主題
│   ├── numbering.xml               ← 清單編號設定（若有清單）
│   ├── footnotes.xml               ← 腳注（若有）
│   ├── endnotes.xml                ← 尾注（若有）
│   ├── header1.xml                 ← 頁首（若有）
│   ├── footer1.xml                 ← 頁尾（若有）
│   ├── media/
│   │   ├── image1.png              ← 嵌入圖片
│   │   └── image2.jpeg
│   └── _rels/
│       └── document.xml.rels       ← document.xml 的關係檔（引用圖片、頁首尾等）
└── docProps/
    ├── app.xml                     ← 應用程式屬性（Word 版本等）
    └── core.xml                    ← 核心屬性（作者、標題、建立時間）
```

---

### 3.2 `[Content_Types].xml`

**作用**：聲明 ZIP 包中每個路徑或副檔名對應的 MIME 類型，是 OOXML 的強制要求。

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <!-- 副檔名預設映射 -->
  <Default Extension="rels"
      ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml"
      ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="jpeg" ContentType="image/jpeg"/>

  <!-- 特定路徑覆蓋 -->
  <Override PartName="/word/document.xml"
      ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml"
      ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml"
      ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>
```

---

### 3.3 關係檔案 `.rels`

OOXML 使用**關係（Relationship）**機制連結各檔案，而非硬編碼路徑。

**`_rels/.rels`**（根層級，指向文件入口）：

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
      Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
      Target="word/document.xml"/>
  <Relationship Id="rId2"
      Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
      Target="docProps/core.xml"/>
</Relationships>
```

**`word/_rels/document.xml.rels`**（document.xml 的引用關係）：

```xml
<Relationships ...>
  <Relationship Id="rId1"
      Type=".../relationships/styles"
      Target="styles.xml"/>
  <Relationship Id="rId2"
      Type=".../relationships/image"
      Target="media/image1.png"/>
  <Relationship Id="rId3"
      Type=".../relationships/header"
      Target="header1.xml"/>
</Relationships>
```

> **重要**：在 `document.xml` 裡用 `r:id="rId2"` 引用圖片，實際路徑由 `.rels` 檔案解析。這是 ODT 與 DOCX 的主要設計差異之一。

---

### 3.4 `word/document.xml` — 文件本文

**命名空間前綴**：OOXML 大量使用 `w:` 前綴（wordprocessingml）。

#### 整體骨架

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
    xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ...>
  <w:body>
    <!-- 段落、表格等內容 -->
    <w:sectPr>  <!-- 節屬性：頁面設定，永遠在最後 -->
      <w:pgSz w:w="11906" w:h="16838"/>       <!-- A4: 寬 210mm = 11906 twips -->
      <w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800"/>
    </w:sectPr>
  </w:body>
</w:document>
```

> **Twips 單位**：OOXML 長度預設使用 twips（1/20 點 = 1/1440 英寸）。A4 寬 21cm ≈ 11906 twips。

#### 段落 `<w:p>`

```xml
<w:p>
  <!-- 段落屬性（可選） -->
  <w:pPr>
    <w:pStyle w:val="Heading1"/>           <!-- 套用的段落樣式 -->
    <w:jc w:val="center"/>                 <!-- 置中對齊 -->
    <w:spacing w:before="240" w:after="120"/>  <!-- 段前/段後間距（twips） -->
  </w:pPr>

  <!-- 文字片段（Run） -->
  <w:r>
    <w:rPr>                                <!-- Run 屬性（行內格式） -->
      <w:b/>                               <!-- 粗體 -->
      <w:color w:val="FF0000"/>            <!-- 紅色 -->
      <w:sz w:val="28"/>                   <!-- 字級 14pt（= 28 半點） -->
    </w:rPr>
    <w:t>這段文字是紅色粗體</w:t>
  </w:r>

  <w:r>
    <w:t xml:space="preserve"> 這是普通文字。</w:t>
    <!-- xml:space="preserve" 保留前後空格 -->
  </w:r>
</w:p>
```

> **半點單位**：OOXML 字級使用半點（half-point）。14pt = `w:sz` 值 28。

#### 表格 `<w:tbl>`

```xml
<w:tbl>
  <w:tblPr>
    <w:tblStyle w:val="TableGrid"/>        <!-- 表格樣式 -->
    <w:tblW w:w="9360" w:type="dxa"/>      <!-- 表格總寬（twips） -->
  </w:tblPr>

  <w:tr>                                   <!-- 列（Table Row） -->
    <w:tc>                                 <!-- 儲存格（Table Cell） -->
      <w:tcPr>
        <w:tcW w:w="4680" w:type="dxa"/>   <!-- 儲存格寬度 -->
      </w:tcPr>
      <w:p><w:r><w:t>儲存格 1</w:t></w:r></w:p>
    </w:tc>
    <w:tc>
      <w:p><w:r><w:t>儲存格 2</w:t></w:r></w:p>
    </w:tc>
  </w:tr>
</w:tbl>
```

#### 圖片（DrawingML）

```xml
<w:p>
  <w:r>
    <w:drawing>
      <wp:inline>                          <!-- 行內圖片 -->
        <wp:extent cx="4572000" cy="2743200"/>  <!-- EMU 單位 -->
        <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
              <pic:blipFill>
                <a:blip r:embed="rId2"/>   <!-- 引用 .rels 中的 rId2 -->
              </pic:blipFill>
              <pic:spPr>
                <a:xfrm><a:ext cx="4572000" cy="2743200"/></a:xfrm>
              </pic:spPr>
            </pic:pic>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing>
  </w:r>
</w:p>
```

> **EMU 單位**：English Metric Units，1 英寸 = 914400 EMU。5cm ≈ 1800000 EMU。

#### 換行

```xml
<w:r><w:br/></w:r>                        <!-- 軟換行（Shift+Enter） -->
<w:r><w:br w:type="page"/></w:r>          <!-- 強制分頁 -->
<w:r><w:tab/></w:r>                       <!-- Tab -->
```

#### 清單（Numbering）

DOCX 的清單較複雜，需搭配 `numbering.xml`：

```xml
<!-- document.xml 中的段落 -->
<w:p>
  <w:pPr>
    <w:numPr>
      <w:ilvl w:val="0"/>                  <!-- 縮排層級（0 = 第一層） -->
      <w:numId w:val="1"/>                 <!-- 引用 numbering.xml 中的編號定義 -->
    </w:numPr>
  </w:pPr>
  <w:r><w:t>清單項目 A</w:t></w:r>
</w:p>
```

---

### 3.5 `word/styles.xml`

```xml
<w:styles ...>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>            <!-- 繼承自 Normal 樣式 -->
    <w:pPr>
      <w:outlineLvl w:val="0"/>
    </w:pPr>
    <w:rPr>
      <w:b/>
      <w:sz w:val="32"/>                   <!-- 16pt -->
      <w:color w:val="2F5496"/>
    </w:rPr>
  </w:style>
</w:styles>
```

---

## 4. 兩種格式對照比較

### 4.1 概念對照表

| 概念 | ODT (ODF) | DOCX (OOXML) |
|------|-----------|---------------|
| **文件內容檔** | `content.xml` | `word/document.xml` |
| **樣式定義** | `styles.xml` | `word/styles.xml` |
| **檔案清單** | `META-INF/manifest.xml` | `[Content_Types].xml` + `_rels/*.rels` |
| **圖片目錄** | `Pictures/` | `word/media/` |
| **段落元素** | `<text:p>` | `<w:p>` |
| **行內格式** | `<text:span style-name="T1">` | `<w:r><w:rPr>...</w:rPr>` |
| **表格** | `<table:table>` | `<w:tbl>` |
| **表格列** | `<table:table-row>` | `<w:tr>` |
| **表格格** | `<table:table-cell>` | `<w:tc>` |
| **圖片容器** | `<draw:frame>` | `<w:drawing><wp:inline>` |
| **軟換行** | `<text:line-break/>` | `<w:br/>` |
| **Tab** | `<text:tab/>` | `<w:tab/>` |
| **具名樣式引用** | `text:style-name="Heading_20_1"` | `<w:pStyle w:val="Heading1"/>` |
| **長度單位** | cm、mm、in、pt（CSS 語法） | twips（文字）、EMU（圖片） |

### 4.2 樣式系統差異

**ODT**：自動樣式（`automatic-styles`）與具名樣式（`office:styles`）分開，前者類似「直接格式化」，後者類似「樣式面板」。

**DOCX**：所有樣式都在 `styles.xml`，用 `w:type="character"` 或 `w:type="paragraph"` 區分；行內的「直接格式化」直接寫在 `<w:rPr>` / `<w:pPr>` 裡，不另存為樣式。

### 4.3 圖片引用機制差異

**ODT**：直接用路徑引用，路徑相對於 ZIP 根目錄：
```xml
<draw:image xlink:href="Pictures/photo.png"/>
```

**DOCX**：用 ID 間接引用，ID 由 `.rels` 檔案解析：
```xml
<!-- document.xml -->
<a:blip r:embed="rId2"/>

<!-- word/_rels/document.xml.rels -->
<Relationship Id="rId2" Target="media/image1.png"/>
```

### 4.4 技術複雜度

| 面向 | ODT | DOCX |
|------|-----|------|
| **規範文件頁數** | 約 800 頁 | 約 6000 頁（含擴充） |
| **命名空間數量** | 約 10–15 個 | 約 30–50 個 |
| **間接引用層數** | 少（直接路徑） | 多（`.rels` 間接引用） |
| **向後相容性** | 一般 | 複雜（有 strict/transitional 兩種模式） |
| **程式解析難度** | 較易 | 較難 |

### 4.5 樣式名稱空格處理

ODT 的 XML attribute 不允許空格，所以 LibreOffice 將空格編碼為 `_20_`（Unicode code point 的十進位）：

```
LibreOffice 樣式名稱  →  XML attribute 值
"Heading 1"          →  "Heading_20_1"
"My Style"           →  "My_20_Style"
"List Bullet"        →  "List_20_Bullet"
```

DOCX 則直接在 `w:val` 裡去掉空格，使用 camelCase 或 PascalCase：

```
Word 樣式名稱   →  w:val
"Heading 1"    →  "Heading1"
"Normal"       →  "Normal"
```

---

## 5. XML 命名空間速查

### ODT 常用命名空間

| 前綴 | URI（縮寫） | 用途 |
|------|------------|------|
| `office:` | `...opendocument:xmlns:office:1.0` | 頂層容器元素 |
| `text:` | `...opendocument:xmlns:text:1.0` | 段落、span、清單 |
| `table:` | `...opendocument:xmlns:table:1.0` | 表格 |
| `draw:` | `...opendocument:xmlns:drawing:1.0` | 圖形、圖片框 |
| `style:` | `...opendocument:xmlns:style:1.0` | 樣式定義 |
| `fo:` | `...xsl-fo-compatible:1.0` | CSS/XSL-FO 格式屬性（字體、顏色等） |
| `svg:` | `...svg-compatible:1.0` | 尺寸屬性（width、height） |
| `xlink:` | `http://www.w3.org/1999/xlink` | 超連結、圖片路徑 |
| `manifest:` | `...opendocument:xmlns:manifest:1.0` | manifest.xml 專用 |

### DOCX 常用命名空間

| 前綴 | 用途 |
|------|------|
| `w:` | 主要 WordprocessingML（段落、表格、樣式） |
| `r:` | 關係 ID（引用圖片、頁首等） |
| `wp:` | DrawingML 位置（行內/浮動圖片容器） |
| `a:` | DrawingML 基本圖形（顏色、字型主題） |
| `pic:` | DrawingML 圖片 |
| `mc:` | Markup Compatibility（版本相容） |
| `w14:` | Word 2010 擴充功能 |

---

## 附錄：手動探索工具

```bash
# 解壓 ODT 觀察結構
unzip -o document.odt -d /tmp/odt_contents

# 美化 XML 輸出（需安裝 xmllint 或 python）
cat /tmp/odt_contents/content.xml | python3 -m xml.dom.minidom

# Python 直接讀取不解壓
import zipfile
with zipfile.ZipFile("document.odt") as z:
    print(z.namelist())                          # 列所有檔案
    print(z.read("content.xml").decode())        # 讀 content.xml

# 同樣方式適用於 .docx
with zipfile.ZipFile("document.docx") as z:
    print(z.namelist())
    print(z.read("word/document.xml").decode())
```

---

*本指南基於 ODF 1.2 規範與 OOXML (ECMA-376) 規範撰寫。*
