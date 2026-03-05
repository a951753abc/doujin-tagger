"""掃描同人誌資料夾，解析檔名並存入資料庫。"""

import json
import os
import re
import sys
import time
from dataclasses import replace as dc_replace
from pathlib import Path

from parser import parse_filename
from models import get_db, init_db, insert_doujinshi, get_setting
import config


def detect_category(filename: str, folder: str, parsed=None, root_path: str = "") -> str:
    """從檔名、資料夾名或解析結果偵測大分類。"""
    # 優先使用 parser 偵測到的商業誌分類
    if parsed and parsed.detected_category:
        return parsed.detected_category
    if re.search(r'同人CG|CG集|ゲームCG', filename) or folder.lower() == "cg":
        return "CG"
    # 根據掃描根目錄名推斷
    if root_path and '商業誌' in str(root_path):
        return "成年コミック"
    return "同人誌"


def get_scan_roots(conn=None) -> list[dict]:
    """從 DB settings 取得掃描路徑。若未設定則回傳空列表。"""
    if conn is None:
        conn = get_db()
    raw = get_setting(conn, "scan_roots", "[]")
    try:
        roots = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        roots = []
    return [
        {"path": Path(r["path"]), "source": r.get("source", "archive"), "label": r.get("label", r["path"])}
        for r in roots if r.get("path")
    ]

# 排除的資料夾
SKIP_DIRS = {"templates", "static", "__pycache__", ".git", "node_modules",
             "$RECYCLE.BIN", "System Volume Information"}

# 圖片副檔名（用於偵測資料夾形式的同人誌）
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}


def is_image_folder(dirpath: str, filenames: list[str]) -> bool:
    """判斷資料夾是否為圖片集（含有圖片檔且無子 zip）。"""
    has_images = False
    for fn in filenames:
        ext = os.path.splitext(fn)[1].lower()
        if ext == '.zip':
            return False  # 含 zip 的不算圖片資料夾
        if ext in IMAGE_EXTS:
            has_images = True
    return has_images


def scan(roots=None, db_path=None):
    conn = get_db(db_path)
    init_db(conn)

    if roots is None:
        roots = get_scan_roots(conn)
        if not roots:
            print("尚未設定掃描路徑。請在 Web 設定頁面新增掃描來源。")
            conn.close()
            return {"total": 0, "inserted": 0, "skipped": 0, "removed": 0,
                    "migrated": 0, "elapsed": 0, "error": "no_scan_roots"}
    init_db(conn)

    total = 0
    inserted = 0
    skipped = 0
    parse_ok = 0
    parse_partial = 0
    start = time.time()

    for root_cfg in roots:
        root = root_cfg["path"]
        source = root_cfg["source"]
        label = root_cfg["label"]

        if not root.exists():
            print(f"  跳過 {label} ({root}): 路徑不存在")
            continue

        print(f"掃描 {label}: {root}")

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            folder = Path(dirpath).name

            # 掃描 zip 檔案
            for fn in filenames:
                if not fn.lower().endswith('.zip'):
                    continue

                total += 1
                filepath = os.path.join(dirpath, fn)

                parsed = parse_filename(fn)
                category = detect_category(fn, folder, parsed, root)
                # 商業誌資料夾中無前綴的檔案：circle→author
                if category == '成年コミック' and not parsed.detected_category:
                    if parsed.circle and not parsed.author:
                        parsed = dc_replace(parsed, author=parsed.circle, circle=None)
                result = insert_doujinshi(conn, parsed, filepath, folder,
                                          category, source)

                if result is not None:
                    inserted += 1
                    if parsed.circle or parsed.author:
                        parse_ok += 1
                    else:
                        parse_partial += 1
                else:
                    skipped += 1

            # 偵測資料夾形式的同人誌（含圖片、無 zip 的資料夾）
            if is_image_folder(dirpath, filenames):
                # 用資料夾名稱作為檔名解析
                folder_name = Path(dirpath).name
                total += 1

                parsed = parse_filename(folder_name + ".zip")
                category = detect_category(folder_name, Path(dirpath).parent.name, parsed, root)
                # 商業誌資料夾中無前綴的資料夾：circle→author
                if category == '成年コミック' and not parsed.detected_category:
                    if parsed.circle and not parsed.author:
                        parsed = dc_replace(parsed, author=parsed.circle, circle=None)
                result = insert_doujinshi(conn, parsed, dirpath, folder,
                                          category, source)

                if result is not None:
                    inserted += 1
                    if parsed.circle or parsed.author:
                        parse_ok += 1
                    else:
                        parse_partial += 1
                else:
                    skipped += 1

                # 不再遞迴進入圖片資料夾的子目錄
                dirnames.clear()

    conn.commit()

    # 清理已不存在的檔案/資料夾（搬移檔案時自動遷移 tag 及 metadata）
    removed = 0
    migrated = 0
    rows = conn.execute("SELECT id, filepath, filename FROM doujinshi").fetchall()
    gone = [(r[0], r[1], r[2]) for r in rows if not os.path.exists(r[1])]

    if gone:
        gone_ids = []
        for old_id, old_path, fname in gone:
            # 用 filename 找同名新紀錄（路徑不同、檔案存在）
            new_row = conn.execute(
                "SELECT id FROM doujinshi WHERE filename = ? AND id != ?",
                (fname, old_id)
            ).fetchone()

            if new_row:
                new_id = new_row[0]
                # 遷移 tags
                old_tags = conn.execute(
                    "SELECT tag_id FROM doujinshi_tags WHERE doujinshi_id = ?",
                    (old_id,)
                ).fetchall()
                for row in old_tags:
                    try:
                        conn.execute(
                            "INSERT INTO doujinshi_tags (doujinshi_id, tag_id) VALUES (?, ?)",
                            (new_id, row[0])
                        )
                    except Exception:
                        pass  # 已存在

                # 遷移手動編輯過的 metadata
                old_data = conn.execute(
                    "SELECT event, circle, author, title, parody, category FROM doujinshi WHERE id = ?",
                    (old_id,)
                ).fetchone()
                if old_data:
                    conn.execute(
                        """UPDATE doujinshi
                           SET event=?, circle=?, author=?, title=?, parody=?, category=?,
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        (*old_data, new_id)
                    )

                # 遷移縮圖
                old_thumb = config.THUMB_DIR / f"{old_id}.webp"
                new_thumb = config.THUMB_DIR / f"{new_id}.webp"
                if old_thumb.exists() and not new_thumb.exists():
                    old_thumb.rename(new_thumb)
                # 也清理 failed marker
                old_failed = config.THUMB_DIR / f"{old_id}.failed"
                if old_failed.exists():
                    old_failed.unlink()

                migrated += 1

            gone_ids.append(old_id)

        if gone_ids:
            placeholders = ",".join("?" * len(gone_ids))
            conn.execute(f"DELETE FROM doujinshi_tags WHERE doujinshi_id IN ({placeholders})", gone_ids)
            conn.execute(f"DELETE FROM doujinshi WHERE id IN ({placeholders})", gone_ids)
            conn.commit()
            removed = len(gone_ids) - migrated

    # 同步 FTS
    try:
        conn.execute("INSERT INTO doujinshi_fts(doujinshi_fts) VALUES('rebuild')")
        conn.commit()
    except Exception:
        pass

    conn.close()
    elapsed = time.time() - start

    result = {
        "total": total,
        "inserted": inserted,
        "skipped": skipped,
        "removed": removed,
        "migrated": migrated,
        "elapsed": round(elapsed, 1),
    }

    print(f"\n掃描完成 ({elapsed:.1f}s)")
    print(f"  總檔案數: {total}")
    print(f"  新增入庫: {inserted}")
    print(f"  已存在跳過: {skipped}")
    print(f"  已移除 (檔案不存在): {removed}")
    if migrated:
        print(f"  已遷移 (檔案搬移): {migrated}")
    print(f"  解析成功 (含社團/作者): {parse_ok}")
    print(f"  部分解析 (僅標題): {parse_partial}")

    return result


if __name__ == '__main__':
    if len(sys.argv) > 1:
        # 手動指定單一路徑
        custom_root = Path(sys.argv[1])
        roots = [{"path": custom_root, "source": "archive", "label": str(custom_root)}]
        scan(roots)
    else:
        scan()
