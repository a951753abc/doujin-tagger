# doujin-tagger

本機 Web 應用，用於管理同人誌與成年漫畫收藏。支援多維度 tag 搜尋、縮圖瀏覽、metadata 編輯、批次操作。

Local web app for managing doujinshi & commercial manga collections with multi-dimensional tag search, thumbnail browsing, and metadata editing.

## 功能特色

- **全文搜尋** -- SQLite FTS5，跨標題、作者、社團、原作搜尋
- **多欄位篩選** -- fuzzy autocomplete 下拉選單，點擊 badge 一鍵篩選
- **縮圖瀏覽** -- 格子（封面牆）/ 列表模式，背景非同步生成 webp 縮圖
- **批次操作** -- 多選後批次加 tag、改原作、改分類
- **重複偵測與合併** -- 日文正規化（平假名/片假名/romaji）自動比對
- **Web 搜尋建議** -- 查詢 DLsite 補全缺漏的 metadata
- **統計 Dashboard** -- 原作、作者、社團、場次 Top N 統計圖
- **外部閱讀器** -- 一鍵用 Honeyview 或任意閱讀器開啟檔案
- **商業誌支援** -- 自動識別 `(成年コミック)`、`(官能小説)` 等分類
- **跨平台** -- Windows、macOS、Linux

## 安裝與啟動

### 環境需求

- **Python 3.9+**（使用了 `list[tuple]` 等型別提示語法）
- pip（Python 套件管理器，通常隨 Python 安裝）

### 步驟

1. **下載專案**

```bash
git clone https://github.com/a951753abc/doujin-tagger.git
cd doujin-tagger
```

2. **安裝相依套件**

```bash
pip install -r requirements.txt
```

這會安裝以下套件：

| 套件 | 用途 |
|------|------|
| Flask | Web 後端框架 |
| Pillow | 縮圖生成（zip 內圖片 → webp） |
| requests | Web 搜尋建議（查 DLsite） |
| beautifulsoup4 | 網頁解析（搭配 requests） |
| pykakasi | 日文正規化（漢字/假名 → romaji） |

> **Windows 注意**: Pillow 和 pykakasi 皆提供預編譯的 wheel，`pip install` 即可，不需要額外的 C 編譯器。

3. **啟動伺服器**

```bash
python app.py
```

4. **開啟瀏覽器**

前往 http://localhost:5000

5. **設定掃描路徑**

首次啟動後，點右上角 **設定** 頁面，新增你的同人誌/漫畫資料夾路徑，然後按 **重新掃描**。

## 設定

設定有三個來源，優先順序由高到低：

### 1. 環境變數

```bash
export DOUJIN_PORT=8080
export DOUJIN_DEBUG=true
export DOUJIN_THUMB_WORKERS=2
```

### 2. config.json

複製範例檔後自行修改：

```bash
cp config.json.example config.json
```

可用選項：

| 鍵 | 預設值 | 說明 |
|----|--------|------|
| `port` | `5000` | 伺服器埠號 |
| `debug` | `false` | Flask 除錯模式 |
| `db_path` | `./doujin.db` | SQLite 資料庫路徑 |
| `thumb_dir` | `./thumbs/` | 縮圖快取目錄 |
| `thumb_size` | `300x400` | 縮圖尺寸（寬x高） |
| `thumb_workers` | `4` | 背景縮圖生成執行緒數 |
| `thumb_quality` | `80` | WebP 壓縮品質（1-100） |
| `request_delay` | `1.5` | Web 搜尋請求間隔（秒） |

### 3. Web UI 設定頁面

在瀏覽器中點 **設定** 可配置：

- **掃描路徑** -- 你的同人誌/漫畫存放資料夾（支援多個，可標記來源類型）
- **閱讀器路徑** -- 外部閱讀程式的執行檔路徑（如 Honeyview）

## 支援的檔名格式

### 同人誌

```
(C106) [社團名 (作者名)] 標題 (原作) [DL版].zip
(COMIC1☆8) [社團名] 標題.zip
[社團名 (作者名)] 標題 (原作).zip
(同人誌) (C90) [社團名 (作者名)] 標題.zip
```

### 商業誌

```
(成年コミック) [作者名] 標題 [DL版].zip
(官能小説・エロライトノベル) [作者名] 標題.zip
```

不符合任何格式的檔案仍會入庫，以完整檔名作為標題。

## 技術架構

- **後端**: Python + Flask + SQLite（FTS5 全文搜尋）
- **前端**: 純 HTML/CSS/JS（無框架、無建置步驟）
- **縮圖**: Pillow 生成 webp，ThreadPoolExecutor 背景非同步處理
- **日文正規化**: pykakasi（漢字/假名 → romaji 比對）

## License

MIT
