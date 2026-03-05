# doujin-tagger

Local web app for managing doujinshi collections with multi-dimensional tag search, thumbnail browsing, and metadata editing.

同人誌收藏管理工具 -- 支援多維度 tag 搜尋、縮圖瀏覽、metadata 編輯、批次操作。

## Features

- **FTS5 full-text search** across title, author, circle, parody
- **Multi-field filtering** with fuzzy autocomplete
- **Thumbnail grid / list view** with lazy background generation
- **Batch operations** -- add tags, update parody/category for multiple items
- **Duplicate detection & merge** with Japanese normalization (hiragana/katakana/romaji)
- **Web enrichment** -- search DLsite for missing metadata
- **Statistics dashboard** -- top parody, author, circle, event charts
- **External reader integration** -- open files with Honeyview or any viewer
- **Cross-platform** -- Windows, macOS, Linux

## Screenshots

<details>
<summary>Search view</summary>

(grid / list view with filters, autocomplete, badge click-to-filter)
</details>

## Quick Start

```bash
git clone https://github.com/your-username/doujin-tagger.git
cd doujin-tagger
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 and go to **Settings** to add your scan paths.

## Configuration

Settings can be configured in three ways (in priority order):

### 1. Environment Variables

```bash
DOUJIN_PORT=8080
DOUJIN_DEBUG=true
DOUJIN_THUMB_WORKERS=2
```

### 2. config.json

Copy `config.json.example` to `config.json`:

```bash
cp config.json.example config.json
```

Available options:

| Key | Default | Description |
|-----|---------|-------------|
| `port` | `5000` | Server port |
| `debug` | `false` | Flask debug mode |
| `db_path` | `./doujin.db` | SQLite database path |
| `thumb_dir` | `./thumbs/` | Thumbnail cache directory |
| `thumb_size` | `300x400` | Thumbnail dimensions |
| `thumb_workers` | `4` | Background thumbnail threads |
| `thumb_quality` | `80` | WebP quality (1-100) |
| `request_delay` | `1.5` | Web search request interval (seconds) |

### 3. Web UI Settings

Go to the **Settings** page to configure:
- **Scan paths** -- directories containing your doujinshi files (zip or image folders)
- **Viewer path** -- external reader program (e.g., Honeyview)

## Filename Format

The parser recognizes doujinshi filenames in common conventions:

```
(C106) [Circle (Author)] Title (Parody) [DL].zip
(COMIC1*8) [Circle] Title.zip
[Circle (Author)] Title (Parody).zip
```

Files that don't match are still indexed with the full filename as title.

## Tech Stack

- **Backend**: Python, Flask, SQLite with FTS5
- **Frontend**: Vanilla HTML/CSS/JS (no build step)
- **Thumbnails**: Pillow, background ThreadPoolExecutor
- **Japanese normalization**: pykakasi

## License

MIT
