"""掃描同人誌資料夾，解析檔名並存入資料庫。"""

import os
import re
import sys
import time
from pathlib import Path

from parser import parse_filename
from models import get_db, init_db, insert_doujinshi


def detect_category(filename: str, folder: str) -> str:
    """從檔名和資料夾名偵測大分類。"""
    fn_lower = filename.lower()
    folder_lower = folder.lower()
    if folder_lower == "cg" or re.search(r'同人CG|CG集|ゲームCG', filename):
        return "CG"
    return "同人誌"


# 多來源掃描設定
SCAN_ROOTS = [
    {"path": Path("I:/同人誌"), "source": "archive", "label": "歸檔區"},
    {"path": Path("H:/"),       "source": "downloads", "label": "下載區"},
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
    if roots is None:
        roots = SCAN_ROOTS

    conn = get_db(db_path)
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
                category = detect_category(fn, folder)
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
                category = detect_category(folder_name, Path(dirpath).parent.name)
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

    # 清理已不存在的檔案/資料夾
    removed = 0
    rows = conn.execute("SELECT id, filepath FROM doujinshi").fetchall()
    gone_ids = [r[0] for r in rows if not os.path.exists(r[1])]
    if gone_ids:
        placeholders = ",".join("?" * len(gone_ids))
        conn.execute(f"DELETE FROM doujinshi_tags WHERE doujinshi_id IN ({placeholders})", gone_ids)
        conn.execute(f"DELETE FROM doujinshi WHERE id IN ({placeholders})", gone_ids)
        conn.commit()
        removed = len(gone_ids)

    # 同步 FTS
    try:
        conn.execute("INSERT INTO doujinshi_fts(doujinshi_fts) VALUES('rebuild')")
        conn.commit()
    except Exception:
        pass

    conn.close()
    elapsed = time.time() - start

    print(f"\n掃描完成 ({elapsed:.1f}s)")
    print(f"  總檔案數: {total}")
    print(f"  新增入庫: {inserted}")
    print(f"  已存在跳過: {skipped}")
    print(f"  已移除 (檔案不存在): {removed}")
    print(f"  解析成功 (含社團/作者): {parse_ok}")
    print(f"  部分解析 (僅標題): {parse_partial}")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        # 手動指定單一路徑
        custom_root = Path(sys.argv[1])
        roots = [{"path": custom_root, "source": "archive", "label": str(custom_root)}]
        scan(roots)
    else:
        scan()
