# 同人誌 TAG 搜尋系統 (doujin-tagger)

## 專案概要

本機 Web 應用，用於管理同人誌收藏，支援多維度 tag 搜尋、一鍵開檔、metadata 編輯。

## 技術架構

- **後端**: Python + Flask（localhost:5000）
- **資料庫**: SQLite + FTS5 全文搜尋（`doujin.db`）
- **前端**: 純 HTML/CSS/JS（無框架）
- **掃描來源**: `I:/同人誌/`（HDD，歸檔區）+ `H:/`（下載區）
- **程式位置**: `L:/doujin-tagger/`（SSD）

## 檔案結構

```
L:/doujin-tagger/
├── parser.py           # 檔名解析（場次/社團/作者/標題/原作）
├── models.py           # DB schema + CRUD + FTS5
├── scan.py             # 多來源掃描（I:/同人誌/ + H:/）zip 及資料夾入庫
├── app.py              # Flask 主程式（路由 + API）
├── templates/
│   └── index.html      # 搜尋主頁（含 tag 編輯、metadata 編輯 modal）
├── static/
│   └── style.css       # 暗色主題樣式
├── doujin.db           # SQLite 資料庫（自動產生）
└── requirements.txt    # flask>=3.0
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

- **doujinshi**: 主表（event, circle, author, title, parody, source 各有索引）
- **tags**: 自訂 tag 表
- **doujinshi_tags**: 多對多關聯
- **doujinshi_fts**: FTS5 虛擬表，自動由觸發器同步

## API 路由

| 方法 | 路由 | 用途 |
|------|------|------|
| GET | `/` | 搜尋主頁 |
| GET | `/api/search` | 搜尋（支援 q, event, circle, author, parody, tags, source, page） |
| GET | `/api/filters` | 篩選選項（各欄位 distinct 值） |
| GET | `/api/doujinshi/<id>` | 單本詳情 |
| PUT | `/api/doujinshi/<id>` | 更新 metadata |
| POST | `/api/doujinshi/<id>/tags` | 新增 tag |
| DELETE | `/api/doujinshi/<id>/tags/<tid>` | 移除 tag |
| GET | `/api/tags` | 所有 tag |
| GET | `/open/<id>` | 用 OS 預設程式開啟 zip |
| POST | `/api/rescan` | 重新掃描 |

## 啟動方式

```bash
cd L:/doujin-tagger
python app.py
# 瀏覽 http://localhost:5000
```

## 統計（2026-03-05）

- 歸檔區 (I:\同人誌): 12,721 筆（含 zip + 資料夾形式）
- 下載區 (H:\): 440 筆
- 總計: 13,161 筆
- 掃描耗時 ~1 秒
