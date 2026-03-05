"""從 title 欄位提取原作名到 parody 欄位"""
import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent / "doujin.db"

# 已知的原作名對照（標準化）
PARODY_NORMALIZE = {
    "FF4": "ファイナルファンタジーIV",
    "FF6": "ファイナルファンタジーVI",
    "FF7": "ファイナルファンタジーVII",
    "FF9": "ファイナルファンタジーIX",
    "FF10": "ファイナルファンタジーX",
    "FF11": "ファイナルファンタジーXI",
    "FF12": "ファイナルファンタジーXII",
    "FF13": "ファイナルファンタジーXIII",
    "FFT": "ファイナルファンタジータクティクス",
    "FF": "ファイナルファンタジー",
    "FGO": "Fate Grand Order",
    "fgo": "Fate Grand Order",
    "DQ3": "ドラゴンクエスト3",
    "DQ5": "ドラゴンクエスト5",
    "DQ8": "ドラゴンクエスト8",
    "SAO": "ソードアート・オンライン",
    "ラブプラス": "ラブプラス",
    "けいおん": "けいおん!",
    "けいおん!": "けいおん!",
    "けいおん! ": "けいおん!",
    "けいおん!!": "けいおん!!",
    "化物語": "化物語",
    "聖剣3": "聖剣伝説3",
    "オリジナル": "オリジナル",
    "よろず": "よろず",
    "ONE PIECE": "ONE PIECE",
    "Angel Beats!": "Angel Beats!",
    "ガンダムSEED DESTINY": "機動戦士ガンダムSEED DESTINY",
    "ガンダムSEED": "機動戦士ガンダムSEED",
    "ゆめりあ": "ゆめりあ",
    "クイーンズブレイド": "クイーンズブレイド",
    "魔法先生ネギま!": "魔法先生ネギま!",
    "ミラクル☆トレイン": "ミラクル☆トレイン",
    "侍魂": "サムライスピリッツ",
    "花咲くいろは": "花咲くいろは",
    "ディーふらぐ！": "ディーふらぐ!",
    "ファイナルファンタジー": "ファイナルファンタジー",
    "Ore no Imouto": "俺の妹がこんなに可愛いわけがない",
    "Ore no imouto ga Konnani Kawaii Wake ga Nai": "俺の妹がこんなに可愛いわけがない",
    "あの日見た花の名前を僕達はまだ知らない": "あの日見た花の名前を僕達はまだ知らない。",
    "Steins Gate": "Steins;Gate",
    "Steins;Gate": "Steins;Gate",
    "Vocaloid": "VOCALOID",
    "ボーカロイド": "VOCALOID",
    "K-ON!": "けいおん!",
    "K-On!": "けいおん!",
    "K-on!": "けいおん!",
    "Touhou": "東方Project",
    "東方": "東方Project",
    "Kantai Collection": "艦隊これくしょん -艦これ-",
    "KanColle": "艦隊これくしょん -艦これ-",
    "Kancolle": "艦隊これくしょん -艦これ-",
    "艦これ": "艦隊これくしょん -艦これ-",
    "テイルズオブジアビス": "テイルズ オブ ジ アビス",
    "テイルズオブヴェスペリア": "テイルズ オブ ヴェスペリア",
    "ロックマンエグゼ": "ロックマンエグゼ",
    "涼宮ハルヒの憂鬱": "涼宮ハルヒの憂鬱",
    "ハルヒ": "涼宮ハルヒの憂鬱",
    "Hayate no Gotoku": "ハヤテのごとく!",
    "To Aru Majutsu no Index": "とある魔術の禁書目録",
    "Toaru Majutsu no Index": "とある魔術の禁書目録",
    "とある魔術の禁書目録": "とある魔術の禁書目録",
    "とある科学の超電磁砲": "とある科学の超電磁砲",
    "Nanoha": "魔法少女リリカルなのは",
    "Mahou Shoujo Lyrical Nanoha": "魔法少女リリカルなのは",
    "マクロスF": "マクロスF",
    "Various": "よろず",
    "Precure": "プリキュア",
    "PreCure": "プリキュア",
    "Doki Doki Precure": "ドキドキ!プリキュア",
    "Smile Precure": "スマイルプリキュア!",
    "Heartcatch Precure": "ハートキャッチプリキュア!",
    "Suite Precure": "スイートプリキュア♪",
    "Saki": "咲 -Saki-",
    "Pokemon": "ポケットモンスター",
    "Idolm@ster": "アイドルマスター",
    "THE IDOLM@STER": "アイドルマスター",
    "Idolmaster": "アイドルマスター",
    "Granblue Fantasy": "グランブルーファンタジー",
    "Sword Art Online": "ソードアート・オンライン",
    "Love Live": "ラブライブ!",
    "Love Live!": "ラブライブ!",
    "Fate stay night": "Fate/stay night",
    "Fate Apocrypha": "Fate/Apocrypha",
    "Fate Grand Order": "Fate Grand Order",
    "Fate EXTRA": "Fate/EXTRA",
    "Shadowverse": "Shadowverse",
    "Gundam Build Fighters": "ガンダムビルドファイターズ",
    "Infinite Stratos": "インフィニット・ストラトス",
    "Strike Witches": "ストライクウィッチーズ",
    "Highschool DxD": "ハイスクールD×D",
    "Dog Days": "DOG DAYS",
    "Kemono Friends": "けものフレンズ",
    "Senran Kagura": "閃乱カグラ",
    "Kill la Kill": "キルラキル",
    "Working!!": "WORKING!!",
    "Working": "WORKING!!",
    "Boku wa Tomodachi ga Sukunai": "僕は友達が少ない",
    "Mayo Chiki": "まよチキ!",
    "Mayo Chiki!": "まよチキ!",
    "Accel World": "アクセル・ワールド",
    "Guilty Gear": "ギルティギア",
    "BLAZBLUE": "BLAZBLUE",
    "Dragon Quest": "ドラゴンクエスト",
    "Original": "オリジナル",
    "original": "オリジナル",
}

# 無效的 parody 值（格式標記等）
INVALID_PARODY = {
    'jpg', 'png', 'zip', 'rar', 'pdf', 'JPG', 'PNG',
    'DL版', 'DL', 'Digital', 'Chinese', '中文', '英訳',
    '別スキャン 2010-01', '別スキャン 2010-03', '別スキャン 2010-04',
    '別スキャン 2010-06',
    'エロ', '非解体', 'JPG化済', 'ページ順修正', 'JPG化',
    'Laugh',  # A Live(Laugh) And More!
    '2', '1', '3',  # 數字不是原作
}


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('PRAGMA journal_mode=WAL')
    total = 0

    # === 1. 從 title 中提取 (parody) ===
    print("=== 1. 從 title 提取原作 ===")
    rows = conn.execute(
        "SELECT id, title, filename FROM doujinshi "
        "WHERE (parody IS NULL OR parody = '') "
        "AND title IS NOT NULL AND title != ''"
    ).fetchall()

    for row_id, title, filename in rows:
        # 找 title 中的 (xxx) 模式
        # 優先取最後一個括號（通常是原作）
        matches = re.findall(r'\(([^)]+)\)', title)
        if not matches:
            continue

        # 取最後一個有效的括號內容
        parody = None
        for m in reversed(matches):
            m_clean = m.strip()
            if m_clean in INVALID_PARODY:
                continue
            if re.match(r'^\d{4}[-/]\d{2}', m_clean):  # 日期
                continue
            if re.match(r'^RJ\d+', m_clean):  # DLsite 編號
                continue
            if m_clean.startswith('別スキャン'):
                continue
            if m_clean.startswith('ページ'):
                continue
            if m_clean.startswith('発行'):
                continue
            if len(m_clean) <= 1:
                continue

            parody = m_clean
            break

        if not parody:
            continue

        # 標準化原作名
        normalized = PARODY_NORMALIZE.get(parody, parody)

        # 從 title 中移除原作部分，清理 title
        # 找到最後一個 (parody) 出現的位置
        last_idx = title.rfind(f'({parody})')
        if last_idx >= 0:
            new_title = title[:last_idx].strip()
            # 移除尾部的 + 附錄
            new_title = re.sub(r'\s*\+.*$', '', new_title).strip()
            # 移除尾部的 [misc]
            new_title = re.sub(r'\s*\[[^\]]*\]\s*$', '', new_title).strip()
            if new_title:
                conn.execute(
                    "UPDATE doujinshi SET parody = ?, title = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (normalized, new_title, row_id)
                )
            else:
                conn.execute(
                    "UPDATE doujinshi SET parody = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (normalized, row_id)
                )
        else:
            conn.execute(
                "UPDATE doujinshi SET parody = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (normalized, row_id)
            )

        total += 1
        if total <= 40:
            print(f"  [{row_id}] {title[:50]} -> parody={normalized}")

    print(f"  小計: {total} 筆")

    # === 2. 從檔名中的關鍵字推斷（第二輪） ===
    print("\n=== 2. 從檔名推斷原作（第二輪） ===")
    kw_total = 0

    keyword_parody_2 = {
        "ネギま": "魔法先生ネギま!",
        "涼宮ハルヒ": "涼宮ハルヒの憂鬱",
        "ハルヒ": "涼宮ハルヒの憂鬱",
        "ストパン": "ストライクウィッチーズ",
        "なのは": "魔法少女リリカルなのは",
        "マクロスF": "マクロスF",
        "マクロス": "マクロスF",
        "ガンダム": "機動戦士ガンダム",
        "ToHeart": "ToHeart2",
        "ToHeart2": "ToHeart2",
        "ONE PIECE": "ONE PIECE",
        "ワンピース": "ONE PIECE",
        "NARUTO": "NARUTO",
        "ナルト": "NARUTO",
        "BLEACH": "BLEACH",
        "ブリーチ": "BLEACH",
        "ロックマン": "ロックマン",
        "テイルズ": "テイルズ",
        "らき☆すた": "らき☆すた",
        "らきすた": "らき☆すた",
        "CLANNAD": "CLANNAD",
        "クラナド": "CLANNAD",
        "ローゼンメイデン": "ローゼンメイデン",
        "ゼロの使い魔": "ゼロの使い魔",
        "禁書目録": "とある魔術の禁書目録",
    }

    rows = conn.execute(
        "SELECT id, filename FROM doujinshi "
        "WHERE (parody IS NULL OR parody = '')"
    ).fetchall()

    for row_id, filename in rows:
        matched = None
        for keyword, parody in keyword_parody_2.items():
            if keyword in filename:
                matched = parody
                break
        if matched:
            conn.execute(
                "UPDATE doujinshi SET parody = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (matched, row_id)
            )
            kw_total += 1
            if kw_total <= 20:
                print(f"  [{row_id}] {filename[:60]} -> {matched}")

    print(f"  小計: {kw_total} 筆")
    total += kw_total

    # === 3. 修復 C77 格式中的 title (仍含 C77 prefix 的) ===
    print("\n=== 3. 修復殘留前綴的 title ===")
    prefix_total = 0
    rows = conn.execute(
        "SELECT id, title FROM doujinshi "
        "WHERE title LIKE 'C77\\_%' OR title LIKE '(同人誌) %' "
        "OR title LIKE '(同人CG%) %'"
    ).fetchall()
    for row_id, title in rows:
        # 移除前綴
        new_title = re.sub(r'^C77_\(同人誌\)_', '', title)
        new_title = re.sub(r'^\(同人(?:誌|CG集?)\)\s*', '', new_title)
        if new_title != title and new_title:
            conn.execute(
                "UPDATE doujinshi SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_title, row_id)
            )
            prefix_total += 1
    print(f"  清理 title 前綴: {prefix_total} 筆")
    total += prefix_total

    conn.commit()

    # === 最終統計 ===
    print(f"\n{'='*60}")
    print(f"本次修改: {total} 筆")

    total_all = conn.execute('SELECT COUNT(*) FROM doujinshi').fetchone()[0]
    for col, label in [('event', '場次'), ('circle', '社團'),
                        ('author', '作者'), ('title', '標題'), ('parody', '原作')]:
        null_count = conn.execute(
            f"SELECT COUNT(*) FROM doujinshi WHERE {col} IS NULL OR {col} = ''"
        ).fetchone()[0]
        has_count = total_all - null_count
        pct = has_count / total_all * 100
        print(f"  {label}: {has_count}/{total_all} ({pct:.1f}%) | 未分類 {null_count}")

    conn.close()


if __name__ == "__main__":
    main()
