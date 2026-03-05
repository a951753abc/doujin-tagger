# 同人誌 TAG 搜尋系統 (doujin-tagger)

## 專案概要

本機 Web 應用，用於管理同人誌收藏，支援多維度 tag 搜尋、縮圖瀏覽、Honeyview 閱讀、metadata 編輯、批次操作。

## 技術架構

- **後端**: Python + Flask（localhost:5000）
- **資料庫**: SQLite + FTS5 全文搜尋（`doujin.db`）
- **前端**: 純 HTML/CSS/JS（無框架）+ 自訂 Autocomplete 元件
- **縮圖**: Pillow 生成 webp，背景 ThreadPoolExecutor 非同步處理
- **閱讀器**: Honeyview（路徑可在設定頁面修改）
- **掃描來源**: 由 Web UI 設定頁面配置（DB settings 表）
- **設定管理**: config.py 集中管理（環境變數 > config.json > 預設值）

## 檔案結構

```
├── config.py               # 集中設定管理（環境變數/config.json/預設值）
├── parser.py               # 檔名解析（場次/社團/作者/標題/原作）
├── models.py               # DB schema + CRUD + FTS5 + 批次操作 + settings
├── scan.py                 # 多來源掃描 zip 及資料夾入庫
├── app.py                  # Flask 主程式（路由 + API）
├── thumbs.py               # 縮圖生成（zip/資料夾 → webp 快取）
├── normalize.py            # 重複偵測與合併
├── web_enrich.py           # Web 搜尋建議（DLsite 等）
├── templates/
│   └── index.html          # SPA 主頁（搜尋/統計/合併/設定）
├── static/
│   ├── style.css           # 暗色主題樣式
│   └── autocomplete.js     # 自訂 fuzzy autocomplete 元件
├── thumbs/                 # 縮圖快取目錄（自動產生，gitignore）
├── doujin.db               # SQLite 資料庫（自動產生，gitignore）
├── config.json             # 使用者設定檔（可選，gitignore）
├── config.json.example     # 設定檔範例
├── requirements.txt        # flask, Pillow, requests, beautifulsoup4, pykakasi
├── LICENSE                 # MIT
└── README.md               # 專案說明
```

## 檔名格式

主要格式：`(場次) [社團名 (作者名)] 標題 (原作) [DL版].zip`

parser.py 支援的變體：
- 底線分隔（C77 時期）
- `(同人誌)` / `(同人CG集)` 前綴
- 前綴垃圾如 `[firelee@2DJGAME]`
- 日期前綴如 `[180529]`
- 無場次、無作者、COMIC1☆N 等特殊場次名

## DB Schema

- **doujinshi**: 主表（event, circle, author, title, parody, category, source 各有索引）
- **tags**: 自訂 tag 表
- **doujinshi_tags**: 多對多關聯
- **doujinshi_fts**: FTS5 虛擬表，自動由觸發器同步
- **settings**: key-value 設定表（viewer_path 等）

## API 路由

| 方法 | 路由 | 用途 |
|------|------|------|
| GET | `/` | 搜尋主頁 |
| GET | `/api/search` | 搜尋（q, event, circle, author, parody, tags, source, category, sort, page） |
| GET | `/api/filters` | 篩選選項（各欄位 distinct 值 + null count） |
| GET | `/api/doujinshi/<id>` | 單本詳情 |
| PUT | `/api/doujinshi/<id>` | 更新 metadata |
| DELETE | `/api/doujinshi/<id>` | 刪除 zip 檔案及 DB 紀錄 |
| POST | `/api/doujinshi/<id>/tags` | 新增 tag |
| DELETE | `/api/doujinshi/<id>/tags/<tid>` | 移除 tag |
| GET | `/api/tags` | 所有 tag |
| GET | `/open/<id>` | 用 OS 預設程式開啟 |
| GET | `/read/<id>` | 用 Honeyview 開啟閱讀 |
| GET | `/api/thumb/<id>` | 取得縮圖（按需背景生成） |
| POST | `/api/batch/tags` | 批次加 tag |
| PUT | `/api/batch/update` | 批次更新欄位 |
| GET | `/api/stats` | 統計 Dashboard 資料 |
| GET | `/api/duplicates` | 偵測重複值 |
| POST | `/api/merge` | 合併重複值 |
| GET/PUT | `/api/settings` | 讀取/更新設定 |
| POST | `/api/doujinshi/<id>/web-search` | Web 搜尋建議 |
| POST | `/api/rescan` | 重新掃描 |

## 前端功能

- **搜尋**: FTS5 全文 + 多欄位交叉篩選，自訂 fuzzy autocomplete
- **檢視模式**: 列表（含小縮圖）/ 格子（封面牆），localStorage 記憶偏好
- **Badge 篩選**: 點擊場次/社團/作者/原作 badge 一鍵篩選
- **批次操作**: checkbox 多選 → 批次加 tag / 改原作 / 改分類
- **鍵盤**: `/` 搜尋、`Esc` 關閉、`j`/`k` 導覽、`Enter` 開啟
- **Toast**: 所有操作回饋（取代 alert）
- **分頁**: 頁碼按鈕群 + 跳頁輸入
- **統計**: 原作/作者/社團/場次 Top N bar chart
- **合併管理**: 偵測重複命名並合併
- **設定**: 掃描路徑 + 閱讀器路徑可由 Web UI 配置
- **最近開啟**: localStorage 記錄最近 20 筆

## 啟動方式

```bash
pip install -r requirements.txt
python app.py
# 瀏覽 http://localhost:5000
# 首次啟動請到「設定」頁面新增掃描路徑
```
