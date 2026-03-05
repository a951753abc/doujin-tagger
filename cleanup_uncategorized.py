"""未分類項目補標腳本：從檔名/資料夾推斷 metadata"""

import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent / "doujin.db"


def update_fields(conn, row_id, **fields):
    """更新指定欄位（只更新目前為空的欄位）"""
    updates = {}
    for k, v in fields.items():
        if v:
            updates[k] = v
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [row_id]
    conn.execute(
        f"UPDATE doujinshi SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        params
    )
    return True


def fix_folder_events(conn):
    """從資料夾名稱推斷場次"""
    print("\n--- 從資料夾補場次 ---")
    total = 0
    # 資料夾名稱就是場次的情況
    folder_event_map = {
        "C77": "C77", "C78": "C78", "C78_3": "C78",
        "C79": "C79", "c80": "C80", "C81": "C81",
        "C83已讀": "C83", "C90": "C90", "C93": "C93",
        "C95": "C95", "COMIC16": "COMIC1☆16",
    }

    for folder, event in folder_event_map.items():
        cur = conn.execute(
            "UPDATE doujinshi SET event = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE folder = ? AND (event IS NULL OR event = '')",
            (event, folder)
        )
        if cur.rowcount:
            print(f"  folder={folder} -> event={event} ({cur.rowcount} 筆)")
            total += cur.rowcount
    return total


def fix_nosuke(conn):
    """NOSUKE 資料夾 -> 作者 NOSUKE，並從角色名推斷原作"""
    print("\n--- NOSUKE 資料夾補標 ---")
    total = 0

    # 先設定作者
    cur = conn.execute(
        "UPDATE doujinshi SET author = 'NOSUKE', updated_at = CURRENT_TIMESTAMP "
        "WHERE folder IN ('NOSUKE', '未讀') AND (author IS NULL OR author = '') "
        "AND filename LIKE '%ふたなり%' OR filename IN ("
        "  SELECT filename FROM doujinshi WHERE folder = 'NOSUKE'"
        ")"
    )
    # 更精確地處理
    rows = conn.execute(
        "SELECT id, filename FROM doujinshi WHERE folder = 'NOSUKE' "
        "AND (author IS NULL OR author = '')"
    ).fetchall()
    for row_id, filename in rows:
        conn.execute(
            "UPDATE doujinshi SET author = 'NOSUKE', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?", (row_id,)
        )
        total += 1
    if total:
        print(f"  NOSUKE 資料夾 -> author=NOSUKE ({total} 筆)")

    # 從角色名推斷原作 (NOSUKE 的內容)
    nosuke_parody_map = {
        "ウォースパイト": "艦隊これくしょん -艦これ-",
        "山城ちゃん": "艦隊これくしょん -艦これ-",
        "エンプラさん": "アズールレーン",
        "ホノルル": "アズールレーン",
        "ボルチモアさん": "アズールレーン",
        "ユニコーンちゃん": "アズールレーン",
        "甘雨さん": "原神",
        "刻晴": "原神",
        "ユウカ": "ブルーアーカイブ",
        "メド": "ブルーアーカイブ",  # メドゥーサ?
        "サテュロスちゃん": "グランブルーファンタジー",
        "シリアス": "アズールレーン",
        "ビカラちゃん": "グランブルーファンタジー",
    }

    parody_total = 0
    for char_name, parody in nosuke_parody_map.items():
        cur = conn.execute(
            "UPDATE doujinshi SET parody = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE filename LIKE ? AND (parody IS NULL OR parody = '') "
            "AND (author = 'NOSUKE' OR folder = 'NOSUKE' OR folder = '未讀')",
            (parody, f"%{char_name}%")
        )
        if cur.rowcount:
            print(f"  {char_name} -> parody={parody} ({cur.rowcount} 筆)")
            parody_total += cur.rowcount

    return total + parody_total


def fix_c77_underscore(conn):
    """修復 C77 底線格式: C77_同人志_[circle]_title / C77_同人志_SERIES_[circle]_title"""
    print("\n--- C77 底線格式修復 ---")
    total = 0
    rows = conn.execute(
        "SELECT id, filename FROM doujinshi "
        "WHERE filename LIKE 'C77\\_同人%' ESCAPE '\\' "
        "AND (circle IS NULL OR circle = '')"
    ).fetchall()

    for row_id, filename in rows:
        # C77_同人志_LOVE_PLUS_[琥珀亭]_Lovecall_RinRin.zip
        # C77_同人志_[circle]_title
        # C77_同人志_TH2环姐_[cocon!(音音)]_桃色夢現.zip
        m = re.search(r'C77_同人志?_(?:(.+?)_)?\[(.+?)\]_(.+?)\.zip', filename)
        if m:
            series = m.group(1)
            circle_raw = m.group(2)
            title_raw = m.group(3).replace('_', ' ')

            updates = {"circle": circle_raw, "title": title_raw}

            # 嘗試解析社團中的作者
            cm = re.match(r'(.+?)\s*\((.+?)\)', circle_raw)
            if cm:
                updates["circle"] = cm.group(1)
                updates["author"] = cm.group(2)

            if series:
                # LOVE_PLUS -> ラブプラス (known mapping)
                series_map = {
                    "LOVE_PLUS": "ラブプラス",
                    "TH2环姐": "ToHeart2",
                }
                updates["parody"] = series_map.get(series, series.replace('_', ' '))

            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            set_parts.append("updated_at = CURRENT_TIMESTAMP")
            params.append(row_id)
            conn.execute(
                f"UPDATE doujinshi SET {', '.join(set_parts)} WHERE id = ?",
                params
            )
            print(f"  [{row_id}] {filename}")
            for k, v in updates.items():
                print(f"       {k}={v}")
            total += 1

    return total


def fix_star_c77(conn):
    """修復 ★(C77)_(同人誌)_[circle]_title 格式"""
    print("\n--- ★(C77) 格式修復 ---")
    total = 0
    rows = conn.execute(
        "SELECT id, filename FROM doujinshi "
        "WHERE filename LIKE '★(C77)%' "
        "AND (circle IS NULL OR circle = '')"
    ).fetchall()

    for row_id, filename in rows:
        m = re.search(r'★\(C77\)_\(同人誌\)_\[(.+?)\]_(.+?)\.zip', filename)
        if m:
            circle = m.group(1)
            title = m.group(2).replace('_', ' ')
            conn.execute(
                "UPDATE doujinshi SET event = 'C77', circle = ?, title = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (circle, title, row_id)
            )
            print(f"  [{row_id}] circle={circle}, title={title}")
            total += 1
    return total


def fix_sp_gcf(conn):
    """修復 小SP@GCF@(C80) 格式"""
    print("\n--- 小SP@GCF 格式修復 ---")
    total = 0
    rows = conn.execute(
        "SELECT id, filename FROM doujinshi "
        "WHERE filename LIKE '小SP@%' "
        "AND (circle IS NULL OR circle = '')"
    ).fetchall()

    for row_id, filename in rows:
        # 小SP@GCF@(C80)(同人誌)[circle(author)]title(parody)(format).zip
        m = re.search(
            r'小SP@.*?@?\(C(\d+)\)\(同人誌\)\[(.+?)\](.+?)\.zip',
            filename
        )
        if m:
            event = f"C{m.group(1)}"
            circle_raw = m.group(2)
            rest = m.group(3)

            updates = {"event": event}

            # 解析社團(作者)
            cm = re.match(r'(.+?)\((.+?)\)', circle_raw)
            if cm:
                updates["circle"] = cm.group(1)
                updates["author"] = cm.group(2)
            else:
                updates["circle"] = circle_raw

            # 解析 title(parody)(format)
            pm = re.match(r'(.+?)\((.+?)\)\(', rest)
            if pm:
                updates["title"] = pm.group(1)
                updates["parody"] = pm.group(2)
            else:
                updates["title"] = rest

            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            set_parts.append("updated_at = CURRENT_TIMESTAMP")
            params.append(row_id)
            conn.execute(
                f"UPDATE doujinshi SET {', '.join(set_parts)} WHERE id = ?",
                params
            )
            print(f"  [{row_id}] {filename}")
            for k, v in updates.items():
                print(f"       {k}={v}")
            total += 1

    return total


def fix_standard_format(conn):
    """嘗試解析標準格式但之前解析失敗的項目"""
    print("\n--- 標準格式重新解析 ---")
    total = 0
    rows = conn.execute(
        "SELECT id, filename FROM doujinshi "
        "WHERE (circle IS NULL OR circle = '') "
        "AND (author IS NULL OR author = '') "
        "AND (parody IS NULL OR parody = '')"
    ).fetchall()

    for row_id, filename in rows:
        name = filename.replace('.zip', '')

        # (同人誌) [Circle (Author)] Title (Parody) [DL版]
        m = re.match(
            r'\(同人(?:誌|CG集)\)\s*\[(.+?)\]\s*(.+)',
            name
        )
        if m:
            circle_raw = m.group(1)
            rest = m.group(2)

            updates = {}
            # circle (author)
            cm = re.match(r'(.+?)\s*\((.+?)\)', circle_raw)
            if cm:
                updates["circle"] = cm.group(1).strip()
                updates["author"] = cm.group(2).strip()
            else:
                updates["circle"] = circle_raw.strip()

            # title (parody) [DL版]
            pm = re.match(r'(.+?)\s*\((.+?)\)\s*(?:\[.+?\])?\s*$', rest)
            if pm:
                updates["title"] = pm.group(1).strip()
                updates["parody"] = pm.group(2).strip()
            else:
                updates["title"] = re.sub(r'\s*\[DL版\]\s*$', '', rest).strip()

            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            set_parts.append("updated_at = CURRENT_TIMESTAMP")
            params.append(row_id)
            conn.execute(
                f"UPDATE doujinshi SET {', '.join(set_parts)} WHERE id = ?",
                params
            )
            print(f"  [{row_id}] {filename}")
            for k, v in updates.items():
                print(f"       {k}={v}")
            total += 1
            continue

        # [Circle (Author)] Title
        m = re.match(r'\[(.+?)\]\s*(.+)', name)
        if m:
            circle_raw = m.group(1)
            rest = m.group(2)

            # 排除 DLsite 編號等
            if re.match(r'max41@', circle_raw):
                continue

            updates = {}
            cm = re.match(r'(.+?)\s*\((.+?)\)', circle_raw)
            if cm:
                updates["circle"] = cm.group(1).strip()
                updates["author"] = cm.group(2).strip()
            else:
                updates["circle"] = circle_raw.strip()

            pm = re.match(r'(.+?)\s*\((.+?)\)\s*(?:\[.+?\])?\s*$', rest)
            if pm:
                updates["title"] = pm.group(1).strip()
                updates["parody"] = pm.group(2).strip()
            else:
                updates["title"] = re.sub(r'\s*\[DL版?\]\s*$', '', rest).strip()

            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            set_parts.append("updated_at = CURRENT_TIMESTAMP")
            params.append(row_id)
            conn.execute(
                f"UPDATE doujinshi SET {', '.join(set_parts)} WHERE id = ?",
                params
            )
            print(f"  [{row_id}] {filename}")
            for k, v in updates.items():
                print(f"       {k}={v}")
            total += 1
            continue

        # (Gunrei Bu...) [circle (author)] title (parody) [lang]
        m = re.match(r'\(.+?\)\s*\[(.+?)\]\s*(.+)', name)
        if m:
            circle_raw = m.group(1)
            rest = m.group(2)

            updates = {}
            cm = re.match(r'(.+?)\s*\((.+?)\)', circle_raw)
            if cm:
                updates["circle"] = cm.group(1).strip()
                updates["author"] = cm.group(2).strip()
            else:
                updates["circle"] = circle_raw.strip()

            pm = re.match(r'(.+?)\s*\((.+?)\)\s*', rest)
            if pm:
                updates["title"] = pm.group(1).strip()
                updates["parody"] = pm.group(2).strip()
            else:
                updates["title"] = rest.strip()

            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            set_parts.append("updated_at = CURRENT_TIMESTAMP")
            params.append(row_id)
            conn.execute(
                f"UPDATE doujinshi SET {', '.join(set_parts)} WHERE id = ?",
                params
            )
            print(f"  [{row_id}] {filename}")
            for k, v in updates.items():
                print(f"       {k}={v}")
            total += 1

    return total


def fix_parody_from_filename(conn):
    """從檔名中的關鍵字推斷原作"""
    print("\n--- 從檔名推斷原作 ---")
    total = 0

    # 關鍵字 -> 原作名
    keyword_parody = {
        "艦隊": "艦隊これくしょん -艦これ-",
        "艦これ": "艦隊これくしょん -艦これ-",
        "艦縛": "艦隊これくしょん -艦これ-",
        "叢雲": "艦隊これくしょん -艦これ-",
        "愛宕": "艦隊これくしょん -艦これ-",
        "19と58": "艦隊これくしょん -艦これ-",  # 19号 & 58号
        "kantai": "艦隊これくしょん -艦これ-",
        "KANCOLLE": "艦隊これくしょん -艦これ-",
        "fgo": "Fate Grand Order",
        "FGO": "Fate Grand Order",
        "カルデア": "Fate Grand Order",
        "サーヴァント": "Fate Grand Order",
        "マスターに淫乱発情": "Fate Grand Order",
        "ブーディカ": "Fate Grand Order",
        "マシュ": "Fate Grand Order",
        "玉藻": "Fate Grand Order",
        "idolmaster": "アイドルマスター",
        "アイドルマスター": "アイドルマスター",
        "アイドルタイム": "アイドルマスター",
        "Pチャン": "アイドルマスター",
        "文香": "アイドルマスター シンデレラガールズ",
        "precure": "プリキュア",
        "プリキュア": "プリキュア",
        "めぐみん": "この素晴らしい世界に祝福を!",
        "エロマンガ先生": "エロマンガ先生",
        "エロマンガ撮影": "オリジナル",
        "ソードア○ト": "ソードアート・オンライン",
        "SAO": "ソードアート・オンライン",
        "アスナ": "ソードアート・オンライン",
        "セーラームーン": "美少女戦士セーラームーン",
        "ザーメンキャプター": "カードキャプターさくら",
        "code_geass": "コードギアス",
        "御坂": "とある科学の超電磁砲",
        "アズールレーン": "アズールレーン",
        "アズールラバーズ": "アズールレーン",
        "扶桑＆山城": "艦隊これくしょん -艦これ-",
        "アローラ": "ポケットモンスター サン・ムーン",
        "グランブルーファンタジー": "グランブルーファンタジー",
        "ぐらずりっ": "グランブルーファンタジー",
        "ブルーアーカイブ": "ブルーアーカイブ",
        "ラグナロクオンライン": "ラグナロクオンライン",
        "ファイナルファンタジー7": "ファイナルファンタジーVII",
        "ティファ": "ファイナルファンタジーVII",
        "東方": "東方Project",
        "幻想入り": "東方Project",
        "ダイミダラー": "健全ロボ ダイミダラー",
        "ロスヴァイセ": "ハイスクールD×D",
        "原神": "原神",
        "ラブライブ": "ラブライブ!",
        "GRIDMAN": "SSSS.GRIDMAN",
    }

    rows = conn.execute(
        "SELECT id, filename FROM doujinshi "
        "WHERE (parody IS NULL OR parody = '')"
    ).fetchall()

    for row_id, filename in rows:
        matched_parody = None
        for keyword, parody in keyword_parody.items():
            if keyword in filename:
                # エロマンガ撮影 is original, not エロマンガ先生
                if keyword == "エロマンガ先生" and "エロマンガ撮影" in filename:
                    continue
                matched_parody = parody
                break

        if matched_parody:
            conn.execute(
                "UPDATE doujinshi SET parody = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (matched_parody, row_id)
            )
            print(f"  [{row_id}] {filename[:60]}... -> {matched_parody}")
            total += 1

    return total


def fix_diogenes(conn):
    """修復缺少左括號的項目"""
    print("\n--- 其他特殊格式修復 ---")
    total = 0

    # ［ディオゲネスクラブ］ -> circle
    cur = conn.execute(
        "UPDATE doujinshi SET circle = 'ディオゲネスクラブ', "
        "title = 'らぶほがおあなるちゃん', "
        "updated_at = CURRENT_TIMESTAMP "
        "WHERE filename LIKE '%ディオゲネスクラブ%' AND (circle IS NULL OR circle = '')"
    )
    if cur.rowcount:
        print(f"  ディオゲネスクラブ 修復 ({cur.rowcount} 筆)")
        total += cur.rowcount

    # 駄猫屋愚猫堂] -> 缺左括號
    cur = conn.execute(
        "UPDATE doujinshi SET circle = '駄猫屋愚猫堂', "
        "title = 'クラスで一番の優等生に告白してから僕が愛奴にされるまで。', "
        "updated_at = CURRENT_TIMESTAMP "
        "WHERE filename LIKE '%駄猫屋愚猫堂%' AND (circle IS NULL OR circle = '')"
    )
    if cur.rowcount:
        print(f"  駄猫屋愚猫堂 修復 ({cur.rowcount} 筆)")
        total += cur.rowcount

    # [生猫亭 (chan shin han) -> 缺右括號
    cur = conn.execute(
        "UPDATE doujinshi SET circle = '生猫亭', author = 'chan shin han', "
        "title = 'FUTANARI MOON BITCH☆', "
        "updated_at = CURRENT_TIMESTAMP "
        "WHERE filename LIKE '%生猫亭%' AND (circle IS NULL OR circle = '')"
    )
    if cur.rowcount:
        print(f"  生猫亭 修復 ({cur.rowcount} 筆)")
        total += cur.rowcount

    # （C90） [瓢屋 (もみお)] -> 全形括號
    m_rows = conn.execute(
        "SELECT id, filename FROM doujinshi "
        "WHERE filename LIKE '（C%' AND (circle IS NULL OR circle = '')"
    ).fetchall()
    for row_id, filename in m_rows:
        m = re.match(r'（C(\d+)）\s*\[(.+?)\]\s*(.+?)\.zip', filename)
        if m:
            event = f"C{m.group(1)}"
            circle_raw = m.group(2)
            title = m.group(3).strip()

            updates = {"event": event}
            cm = re.match(r'(.+?)\s*\((.+?)\)', circle_raw)
            if cm:
                updates["circle"] = cm.group(1).strip()
                updates["author"] = cm.group(2).strip()
            else:
                updates["circle"] = circle_raw

            # title (parody)
            pm = re.match(r'(.+?)\s*\((.+?)\)\s*$', title)
            if pm:
                # 排除 (jpg) 等格式標記
                if pm.group(2) not in ('jpg', 'png', 'zip'):
                    updates["title"] = pm.group(1).strip()
                    updates["parody"] = pm.group(2).strip()
                else:
                    updates["title"] = title
            else:
                updates["title"] = title

            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                params.append(v)
            set_parts.append("updated_at = CURRENT_TIMESTAMP")
            params.append(row_id)
            conn.execute(
                f"UPDATE doujinshi SET {', '.join(set_parts)} WHERE id = ?",
                params
            )
            print(f"  [{row_id}] {filename[:60]}")
            for k, v in updates.items():
                print(f"       {k}={v}")
            total += 1

    return total


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    total = 0

    print("=" * 60)
    print("未分類項目補標")
    print("=" * 60)

    total += fix_folder_events(conn)
    total += fix_nosuke(conn)
    total += fix_c77_underscore(conn)
    total += fix_star_c77(conn)
    total += fix_sp_gcf(conn)
    total += fix_diogenes(conn)
    total += fix_standard_format(conn)
    total += fix_parody_from_filename(conn)

    conn.commit()

    # 統計
    print("\n" + "=" * 60)
    print(f"總計補標: {total} 筆")

    remaining = conn.execute(
        "SELECT COUNT(*) FROM doujinshi "
        "WHERE (event IS NULL OR event = '') "
        "AND (circle IS NULL OR circle = '') "
        "AND (author IS NULL OR author = '') "
        "AND (parody IS NULL OR parody = '')"
    ).fetchone()[0]
    print(f"仍完全未分類: {remaining} 筆")

    for col, label in [("event", "場次"), ("circle", "社團"),
                        ("author", "作者"), ("parody", "原作")]:
        null_count = conn.execute(
            f"SELECT COUNT(*) FROM doujinshi "
            f"WHERE {col} IS NULL OR {col} = ''"
        ).fetchone()[0]
        print(f"  {label} 未分類: {null_count} 筆")

    conn.close()


if __name__ == "__main__":
    main()
