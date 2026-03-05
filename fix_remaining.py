"""修復剩餘未分類項目"""
import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent / "doujin.db"


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('PRAGMA journal_mode=WAL')
    total = 0

    # === 1. C93 等缺社團格式修復 ===
    print("=== 1. C93 等缺社團格式修復 ===")
    rows = conn.execute(
        "SELECT id, filename, event FROM doujinshi "
        "WHERE (circle IS NULL OR circle = '') "
        "AND filename LIKE '(C%'"
    ).fetchall()

    for row_id, filename, existing_event in rows:
        name = filename.replace('.zip', '')

        # (C93) 姉ヶ丘三丁目 (おきゅうり)] こたつの中こたつの外 (オリジナル)
        m = re.match(r'\(C(\d+)\)\s*(.+?)\s*\((.+?)\)\]\s*(.+?)(?:\s*\((.+?)\))?\s*$', name)
        if m:
            updates = {}
            if not existing_event:
                updates['event'] = f'C{m.group(1)}'
            updates['circle'] = m.group(2).strip()
            updates['author'] = m.group(3).strip()
            rest = m.group(4).strip()
            parody = m.group(5)
            updates['title'] = rest
            if parody:
                updates['parody'] = parody
            _apply_updates(conn, row_id, updates)
            print(f"  [{row_id}] broken bracket: {updates}")
            total += 1
            continue

        # (C93)title (parody) - no circle
        m = re.match(r'\(C(\d+)\)\s*(.+?)(?:\s*\((.+?)\))?\s*$', name)
        if m:
            updates = {}
            if not existing_event:
                updates['event'] = f'C{m.group(1)}'
            title = m.group(2).strip()
            parody = m.group(3)
            updates['title'] = title
            if parody:
                updates['parody'] = parody
            _apply_updates(conn, row_id, updates)
            print(f"  [{row_id}] title={title}" + (f", parody={parody}" if parody else ""))
            total += 1

    # === 2. 特殊括號修復 ===
    print("\n=== 2. 特殊括號修復 ===")
    # (神戸かわさき造船これくしょん2)] [めんてい処 (めんていやくな)] ろーちゃんにだんけだんけ
    row = conn.execute("SELECT id FROM doujinshi WHERE id = 10229 AND (circle IS NULL OR circle = '')").fetchone()
    if row:
        conn.execute(
            "UPDATE doujinshi SET event = '神戸かわさき造船これくしょん2', "
            "circle = 'めんてい処', author = 'めんていやくな', "
            "title = 'ろーちゃんにだんけだんけ', "
            "parody = '艦隊これくしょん -艦これ-', "
            "updated_at = CURRENT_TIMESTAMP WHERE id = 10229"
        )
        print("  [10229] 修復完成")
        total += 1

    # === 3. 未分類 title(parody) 格式 ===
    print("\n=== 3. 未分類 title(parody) 格式 ===")
    rows = conn.execute(
        "SELECT id, filename FROM doujinshi "
        "WHERE folder = '未分類' AND (circle IS NULL OR circle = '') "
        "AND (parody IS NULL OR parody = '')"
    ).fetchall()

    for row_id, filename in rows:
        name = filename.replace('.zip', '')
        m = re.search(r'\(([^)]+)\)\s*$', name)
        if m:
            parody = m.group(1)
            title = name[:m.start()].strip()
            if parody not in ('jpg', 'png', 'zip', 'pdf'):
                conn.execute(
                    "UPDATE doujinshi SET title = ?, parody = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (title, parody, row_id)
                )
                print(f"  [{row_id}] title={title[:40]}, parody={parody}")
                total += 1

    # === 4. CG 資料夾修復 ===
    print("\n=== 4. CG 資料夾修復 ===")
    manual_cg = [
        (8329, {"title": "裏マヨナカの悪戯と秘密のテレビ", "parody": "ペルソナ4"}),
        (8456, {"title": "エロマンガ撮影日和", "parody": "オリジナル"}),
        (8458, {"title": "ソードア○ト・オンラインはぁはぁＣＧ集", "parody": "ソードアート・オンライン"}),
        (8459, {"title": "ソードア○ト・オンライン２はぁはぁＣＧ集", "parody": "ソードアート・オンライン"}),
        (8461, {"title": "種付けおじさん幻想入り", "parody": "東方Project"}),
        (8462, {"title": "種付けおじさん幻想入り２", "parody": "東方Project"}),
    ]
    for rid, updates in manual_cg:
        existing = conn.execute(
            "SELECT parody FROM doujinshi WHERE id = ?", (rid,)
        ).fetchone()
        if existing and (not existing[0] or existing[0] == ''):
            _apply_updates(conn, rid, updates)
            print(f"  [{rid}] {updates}")
            total += 1

    # === 5. 其他資料夾沒社團的 ===
    print("\n=== 5. 其他資料夾沒社團修復 ===")
    rows = conn.execute(
        "SELECT id, folder, filename FROM doujinshi "
        "WHERE (circle IS NULL OR circle = '') "
        "AND folder NOT IN ('未分類', 'C93', 'cg', 'NOSUKE') "
        "ORDER BY folder, filename"
    ).fetchall()

    for row_id, folder, filename in rows:
        name = filename.replace('.zip', '')
        updates = {}

        # [Circle (Author)] Title (Parody)
        m = re.match(r'\[([^\]]+)\]\s*(.+)', name)
        if m:
            circle_raw = m.group(1)
            rest = m.group(2)
            if re.match(r'(firelee|max41|DL|RJ\d|中文)', circle_raw):
                continue

            cm = re.match(r'(.+?)\s*\((.+?)\)', circle_raw)
            if cm:
                updates['circle'] = cm.group(1).strip()
                updates['author'] = cm.group(2).strip()
            else:
                updates['circle'] = circle_raw.strip()

            rest = re.sub(r'\s*\[(Chinese|中文|DL版?|Digital|英訳)\]\s*', ' ', rest).strip()
            pm = re.match(r'(.+?)\s*\(([^)]+)\)\s*$', rest)
            if pm and pm.group(2) not in ('jpg', 'png'):
                updates['title'] = pm.group(1).strip()
                existing_parody = conn.execute(
                    "SELECT parody FROM doujinshi WHERE id = ?", (row_id,)
                ).fetchone()[0]
                if not existing_parody:
                    updates['parody'] = pm.group(2)
            else:
                updates['title'] = rest

        # title (parody) - no brackets at all
        if not updates:
            m = re.match(r'(.+?)\s*\(([^)]+)\)\s*$', name)
            if m and m.group(2) not in ('jpg', 'png', 'zip'):
                updates['title'] = m.group(1).strip()
                existing_parody = conn.execute(
                    "SELECT parody FROM doujinshi WHERE id = ?", (row_id,)
                ).fetchone()[0]
                if not existing_parody:
                    updates['parody'] = m.group(2)

        if updates:
            _apply_updates(conn, row_id, updates)
            total += 1
            parts = [f"{k}={v}" for k, v in updates.items()]
            print(f"  [{row_id}] {folder}/{filename[:50]}  ->  {', '.join(parts)}")

    # === 6. 手動補標特殊項目 ===
    print("\n=== 6. 手動補標 ===")
    manual_fixes = [
        (10733, {"circle": "千本トリイ", "title": "ダークサイドエンジェルエスカレーション完全版"}),
        (10253, {"title": "3人仲良くお風呂の時間", "parody": "エロマンガ先生"}),
        (10259, {"title": "KANCOLLE RACE QUEEN R-18", "parody": "艦隊これくしょん -艦これ-"}),
        (10260, {"title": "kantai", "parody": "艦隊これくしょん -艦これ-"}),
        (10265, {"title": "precure", "parody": "プリキュア"}),
        (10267, {"title": "SAOn REVERSE", "parody": "ソードアート・オンライン"}),
        (10268, {"title": "SSSS.GRIDMANファンブック 侵略されてるぞっ!", "parody": "SSSS.GRIDMAN"}),
        (10270, {"title": "ToLOVEleS", "parody": "To LOVEる -とらぶる-"}),
        (10710, {"title": "ぐらずりっ!-決戦-乳の古戦場", "parody": "グランブルーファンタジー"}),
        (10714, {"title": "それいけ！めぐみん盗賊団", "parody": "この素晴らしい世界に祝福を!"}),
        (10716, {"title": "ねえねえPチャンHしよ？", "parody": "アイドルマスター シンデレラガールズ"}),
        (10720, {"title": "まじめなありすとおませな桃華", "parody": "アイドルマスター シンデレラガールズ"}),
        (10723, {"title": "わくわくカルデアコレクション", "parody": "Fate Grand Order"}),
        (10724, {"title": "アズールラバーズ vol.01 扶桑＆山城", "parody": "アズールレーン"}),
        (10725, {"title": "アローラ人妻温泉旅行", "parody": "ポケットモンスター サン・ムーン"}),
        (10731, {"title": "ザーメンキャプターさくら", "parody": "カードキャプターさくら"}),
        (10732, {"title": "システムですから アイドルタイム3", "parody": "アイドルマスター"}),
        (10739, {"title": "ロスヴァイセックス", "parody": "ハイスクールD×D"}),
        (10741, {"title": "仕事上がりのブーディカは、まるで我慢が出来ません。", "parody": "Fate Grand Order"}),
        (10742, {"title": "令呪をもって命ずる-マスターに淫乱発情し、ご奉仕するのだ。", "parody": "Fate Grand Order"}),
        (10747, {"title": "叢雲開発記録", "parody": "艦隊これくしょん -艦これ-"}),
        (10754, {"title": "悪の帝国？いいえ性技の味方です！！", "parody": "健全ロボ ダイミダラー"}),
        (10755, {"title": "教えて愛宕さん", "parody": "艦隊これくしょん -艦これ-"}),
        (10757, {"title": "文香の秘密", "parody": "アイドルマスター シンデレラガールズ"}),
        (10759, {"title": "男の娘提督が19と58に逆レされちゃう本", "parody": "艦隊これくしょん -艦これ-"}),
        (10766, {"title": "艦縛これくしよん「正規空母飛龍」", "parody": "艦隊これくしょん -艦これ-"}),
        (10767, {"title": "艦隊メチャシコレクション", "parody": "艦隊これくしょん -艦これ-"}),
        (10768, {"title": "花金 ランチキオーバー！", "parody": "アイドルマスター"}),
        (5573, {"title": "からくりと母"}),
        (5577, {"title": "スウィートマシュバレンタイン", "parody": "Fate Grand Order"}),
        (5584, {"title": "良妻デリヘル玉藻ちゃん", "parody": "Fate Grand Order"}),
        (10708, {"title": "SAOアスナ-爆乳戦闘員化洗脳", "parody": "ソードアート・オンライン"}),
        (10715, {"title": "なのです!肆", "parody": "艦隊これくしょん -艦これ-"}),
        (10726, {"title": "アンバーの本", "parody": "原神"}),
        (10729, {"title": "カルミナ活動記録", "parody": "グランブルーファンタジー"}),
        (10744, {"title": "加音町響奏曲2", "parody": "VOCALOID"}),
    ]
    for rid, updates in manual_fixes:
        existing = conn.execute("SELECT circle FROM doujinshi WHERE id = ?", (rid,)).fetchone()
        if existing is not None:
            _apply_updates(conn, rid, updates)
            parts = [f"{k}={v}" for k, v in updates.items()]
            print(f"  [{rid}] {', '.join(parts)}")
            total += 1

    conn.commit()

    # === 最終統計 ===
    print(f"\n{'='*60}")
    print(f"本次修改: {total} 筆")

    total_all = conn.execute('SELECT COUNT(*) FROM doujinshi').fetchone()[0]
    for col, label in [('event', '場次'), ('circle', '社團'),
                        ('author', '作者'), ('parody', '原作')]:
        null_count = conn.execute(
            f"SELECT COUNT(*) FROM doujinshi WHERE {col} IS NULL OR {col} = ''"
        ).fetchone()[0]
        has_count = total_all - null_count
        pct = has_count / total_all * 100
        print(f"  {label}: {has_count}/{total_all} ({pct:.1f}%) | 未分類 {null_count}")

    fully_empty = conn.execute(
        "SELECT COUNT(*) FROM doujinshi "
        "WHERE (event IS NULL OR event = '') "
        "AND (circle IS NULL OR circle = '') "
        "AND (author IS NULL OR author = '') "
        "AND (parody IS NULL OR parody = '')"
    ).fetchone()[0]
    print(f"\n  完全未分類: {fully_empty} 筆")

    conn.close()


def _apply_updates(conn, row_id, updates):
    set_parts = [f"{k} = ?" for k in updates]
    set_parts.append("updated_at = CURRENT_TIMESTAMP")
    params = list(updates.values()) + [row_id]
    conn.execute(
        f"UPDATE doujinshi SET {', '.join(set_parts)} WHERE id = ?",
        params
    )


if __name__ == "__main__":
    main()
