"""SQLite 資料庫模組"""

import sqlite3
import json
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "doujin.db"


def get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None):
    close = False
    if conn is None:
        conn = get_db()
        close = True

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS doujinshi (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT NOT NULL,
            filepath    TEXT NOT NULL UNIQUE,
            folder      TEXT,
            event       TEXT,
            circle      TEXT,
            author      TEXT,
            title       TEXT,
            parody      TEXT,
            is_dl       INTEGER DEFAULT 0,
            category    TEXT DEFAULT '同人誌',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS doujinshi_tags (
            doujinshi_id INTEGER NOT NULL,
            tag_id       INTEGER NOT NULL,
            PRIMARY KEY (doujinshi_id, tag_id),
            FOREIGN KEY (doujinshi_id) REFERENCES doujinshi(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id)       REFERENCES tags(id)       ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_event  ON doujinshi(event);
        CREATE INDEX IF NOT EXISTS idx_circle ON doujinshi(circle);
        CREATE INDEX IF NOT EXISTS idx_author ON doujinshi(author);
        CREATE INDEX IF NOT EXISTS idx_parody ON doujinshi(parody);
    """)

    # FTS5 要單獨建（不能放在 executescript 的 IF NOT EXISTS 中會出問題）
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE doujinshi_fts USING fts5(
                filename, title, circle, author, parody,
                content='doujinshi',
                content_rowid='id'
            )
        """)
    except sqlite3.OperationalError:
        pass  # 已存在

    # FTS 同步觸發器
    for trigger_sql in [
        """CREATE TRIGGER IF NOT EXISTS fts_ai AFTER INSERT ON doujinshi BEGIN
            INSERT INTO doujinshi_fts(rowid, filename, title, circle, author, parody)
            VALUES (new.id, new.filename, new.title, new.circle, new.author, new.parody);
        END""",
        """CREATE TRIGGER IF NOT EXISTS fts_ad AFTER DELETE ON doujinshi BEGIN
            INSERT INTO doujinshi_fts(doujinshi_fts, rowid, filename, title, circle, author, parody)
            VALUES ('delete', old.id, old.filename, old.title, old.circle, old.author, old.parody);
        END""",
        """CREATE TRIGGER IF NOT EXISTS fts_au AFTER UPDATE ON doujinshi BEGIN
            INSERT INTO doujinshi_fts(doujinshi_fts, rowid, filename, title, circle, author, parody)
            VALUES ('delete', old.id, old.filename, old.title, old.circle, old.author, old.parody);
            INSERT INTO doujinshi_fts(rowid, filename, title, circle, author, parody)
            VALUES (new.id, new.filename, new.title, new.circle, new.author, new.parody);
        END""",
    ]:
        try:
            conn.execute(trigger_sql)
        except sqlite3.OperationalError:
            pass

    # Migration: 既有 DB 加 category 欄位
    try:
        conn.execute("ALTER TABLE doujinshi ADD COLUMN category TEXT DEFAULT '同人誌'")
    except sqlite3.OperationalError:
        pass  # 已存在
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON doujinshi(category)")
    except sqlite3.OperationalError:
        pass

    # Migration: 加 source 欄位（archive=歸檔區, downloads=下載區）
    try:
        conn.execute("ALTER TABLE doujinshi ADD COLUMN source TEXT DEFAULT 'archive'")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON doujinshi(source)")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    if close:
        conn.close()


def insert_doujinshi(conn, parsed, filepath: str, folder: str,
                     category: str = "同人誌",
                     source: str = "archive") -> Optional[int]:
    """插入一筆同人誌紀錄，已存在則跳過。回傳 id 或 None。"""
    try:
        cur = conn.execute(
            """INSERT INTO doujinshi (filename, filepath, folder, event, circle, author, title, parody, is_dl, category, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                Path(filepath).name,
                filepath,
                folder,
                parsed.event,
                parsed.circle,
                parsed.author,
                parsed.title,
                parsed.parody,
                1 if parsed.is_dl else 0,
                category,
                source,
            )
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # filepath UNIQUE 衝突，已存在


SORT_COLUMNS = {"title", "event", "circle", "author", "parody", "created_at", "filename"}


def search_doujinshi(conn, query="", event="", circle="", author="", parody="",
                     tags=None, page=1, per_page=50,
                     sort="event", order="desc", category="", source=""):
    """多條件交叉篩選搜尋。"""
    conditions = []
    params = []

    if category:
        conditions.append("d.category = ?")
        params.append(category)

    if source:
        conditions.append("d.source = ?")
        params.append(source)

    if query:
        conditions.append("d.id IN (SELECT rowid FROM doujinshi_fts WHERE doujinshi_fts MATCH ?)")
        # FTS5 query: 加 * 支援前綴搜尋
        fts_query = " ".join(f'"{w}"*' for w in query.split() if w)
        params.append(fts_query)

    if event == "__null__":
        conditions.append("(d.event IS NULL OR d.event = '')")
    elif event:
        conditions.append("d.event = ?")
        params.append(event)

    if circle == "__null__":
        conditions.append("(d.circle IS NULL OR d.circle = '')")
    elif circle:
        conditions.append("d.circle = ?")
        params.append(circle)

    if author == "__null__":
        conditions.append("(d.author IS NULL OR d.author = '')")
    elif author:
        conditions.append("d.author = ?")
        params.append(author)

    if parody == "__null__":
        conditions.append("(d.parody IS NULL OR d.parody = '')")
    elif parody:
        conditions.append("d.parody = ?")
        params.append(parody)

    if tags:
        tag_list = tags if isinstance(tags, list) else [tags]
        placeholders = ",".join("?" * len(tag_list))
        conditions.append(f"""d.id IN (
            SELECT dt.doujinshi_id FROM doujinshi_tags dt
            JOIN tags t ON t.id = dt.tag_id
            WHERE t.name IN ({placeholders})
            GROUP BY dt.doujinshi_id
            HAVING COUNT(DISTINCT t.name) = ?
        )""")
        params.extend(tag_list)
        params.append(len(tag_list))

    where = " AND ".join(conditions) if conditions else "1=1"

    sort_col = sort if sort in SORT_COLUMNS else "event"
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"

    # 計算總數
    count_sql = f"SELECT COUNT(*) FROM doujinshi d WHERE {where}"
    total = conn.execute(count_sql, params).fetchone()[0]

    # 取得分頁結果
    offset = (page - 1) * per_page
    data_sql = f"""
        SELECT d.*, GROUP_CONCAT(t.name, '||') as tag_names,
               GROUP_CONCAT(t.id, '||') as tag_ids
        FROM doujinshi d
        LEFT JOIN doujinshi_tags dt ON d.id = dt.doujinshi_id
        LEFT JOIN tags t ON t.id = dt.tag_id
        WHERE {where}
        GROUP BY d.id
        ORDER BY d.{sort_col} {sort_dir}, d.title
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(data_sql, params + [per_page, offset]).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        tag_names = item.pop('tag_names', None)
        tag_ids = item.pop('tag_ids', None)
        item['tags'] = []
        if tag_names:
            names = tag_names.split('||')
            ids = tag_ids.split('||')
            item['tags'] = [{"id": int(i), "name": n} for i, n in zip(ids, names)]
        results.append(item)

    return {"total": total, "page": page, "per_page": per_page, "results": results}


def get_doujinshi(conn, doujinshi_id: int):
    row = conn.execute(
        """SELECT d.*, GROUP_CONCAT(t.name, '||') as tag_names,
                  GROUP_CONCAT(t.id, '||') as tag_ids
           FROM doujinshi d
           LEFT JOIN doujinshi_tags dt ON d.id = dt.doujinshi_id
           LEFT JOIN tags t ON t.id = dt.tag_id
           WHERE d.id = ?
           GROUP BY d.id""",
        (doujinshi_id,)
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    tag_names = item.pop('tag_names', None)
    tag_ids = item.pop('tag_ids', None)
    item['tags'] = []
    if tag_names:
        names = tag_names.split('||')
        ids = tag_ids.split('||')
        item['tags'] = [{"id": int(i), "name": n} for i, n in zip(ids, names)]
    return item


def delete_doujinshi(conn, doujinshi_id: int):
    """刪除一筆同人誌紀錄及其 tag 關聯。"""
    conn.execute("DELETE FROM doujinshi_tags WHERE doujinshi_id = ?", (doujinshi_id,))
    conn.execute("DELETE FROM doujinshi WHERE id = ?", (doujinshi_id,))
    conn.commit()


def update_doujinshi(conn, doujinshi_id: int, fields: dict):
    allowed = {'event', 'circle', 'author', 'title', 'parody', 'category'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [doujinshi_id]
    conn.execute(
        f"UPDATE doujinshi SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        params
    )
    conn.commit()


def add_tag(conn, doujinshi_id: int, tag_name: str) -> dict:
    tag_name = tag_name.strip()
    # 取得或建立 tag
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
    if row:
        tag_id = row[0]
    else:
        cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
        tag_id = cur.lastrowid
    # 關聯
    try:
        conn.execute("INSERT INTO doujinshi_tags (doujinshi_id, tag_id) VALUES (?, ?)",
                      (doujinshi_id, tag_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # 已存在
    return {"id": tag_id, "name": tag_name}


def remove_tag(conn, doujinshi_id: int, tag_id: int):
    conn.execute("DELETE FROM doujinshi_tags WHERE doujinshi_id = ? AND tag_id = ?",
                  (doujinshi_id, tag_id))
    conn.execute(
        "DELETE FROM tags WHERE id = ? AND NOT EXISTS "
        "(SELECT 1 FROM doujinshi_tags WHERE tag_id = ?)",
        (tag_id, tag_id))
    conn.commit()


def get_all_tags(conn):
    rows = conn.execute(
        """SELECT t.id, t.name, COUNT(dt.doujinshi_id) as count
           FROM tags t
           LEFT JOIN doujinshi_tags dt ON t.id = dt.tag_id
           GROUP BY t.id
           ORDER BY count DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_filter_options(conn):
    """取得各欄位的 distinct 值，用於前端下拉選單。"""
    result = {}
    for col in ['event', 'circle', 'author', 'parody']:
        order = f"{col} ASC"
        rows = conn.execute(
            f"SELECT {col}, COUNT(*) as cnt FROM doujinshi WHERE {col} IS NOT NULL AND {col} != '' GROUP BY {col} ORDER BY {order}"
        ).fetchall()
        result[col] = [{"value": r[0], "count": r[1]} for r in rows]
        # 附上未分類筆數
        null_count = conn.execute(
            f"SELECT COUNT(*) FROM doujinshi WHERE {col} IS NULL OR {col} = ''"
        ).fetchone()[0]
        result[f"{col}_null_count"] = null_count

    # 來源統計
    source_rows = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM doujinshi GROUP BY source"
    ).fetchall()
    result['sources'] = {r[0]: r[1] for r in source_rows}
    return result


def batch_add_tag(conn, doujinshi_ids: list, tag_name: str) -> dict:
    """對多筆同人誌加上同一個 tag。"""
    tag_name = tag_name.strip()
    if not tag_name or not doujinshi_ids:
        return {"added": 0}
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
    if row:
        tag_id = row[0]
    else:
        cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
        tag_id = cur.lastrowid
    added = 0
    for did in doujinshi_ids:
        try:
            conn.execute("INSERT INTO doujinshi_tags (doujinshi_id, tag_id) VALUES (?, ?)",
                         (did, tag_id))
            added += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return {"added": added}


def batch_update(conn, doujinshi_ids: list, fields: dict) -> dict:
    """對多筆同人誌更新相同欄位。"""
    allowed = {'event', 'circle', 'author', 'title', 'parody', 'category'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates or not doujinshi_ids:
        return {"updated": 0}
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    placeholders = ",".join("?" * len(doujinshi_ids))
    params = list(updates.values()) + doujinshi_ids
    cur = conn.execute(
        f"UPDATE doujinshi SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
        params
    )
    conn.commit()
    return {"updated": cur.rowcount}
