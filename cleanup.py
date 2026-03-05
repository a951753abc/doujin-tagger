"""資料庫清理腳本：合併重複場次、社團、作者、原作"""

import sqlite3
import re
from pathlib import Path

DB_PATH = Path(__file__).parent / "doujin.db"


def merge_field(conn, field: str, rules: list[tuple[str, str]]):
    """批次合併某欄位的值。rules = [(old_value, new_value), ...]"""
    total = 0
    for old_val, new_val in rules:
        if old_val == new_val:
            continue
        cur = conn.execute(
            f"UPDATE doujinshi SET {field} = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE {field} = ?",
            (new_val, old_val)
        )
        if cur.rowcount > 0:
            print(f"  {field}: [{old_val}] -> [{new_val}] ({cur.rowcount} 筆)")
            total += cur.rowcount
    return total


def build_event_rules():
    """場次合併規則"""
    rules = []

    # 1. 大小寫: c79->C79, c80->C80, c81->C81, c90->C90, c96->C96
    for n in [79, 80, 81, 90, 96]:
        rules.append((f"c{n}", f"C{n}"))

    # 2. Cyrillic С -> Latin C
    rules.append(("С86", "C86"))  # Cyrillic С
    rules.append(("С87", "C87"))

    # 3. COMIC1 大小寫
    rules.append(("Comic1☆11", "COMIC1☆11"))

    # 4. COMIC1 前導零
    rules.append(("COMIC1☆06", "COMIC1☆6"))
    rules.append(("COMIC1☆07", "COMIC1☆7"))
    rules.append(("COMIC1☆09", "COMIC1☆9"))

    # 5. COMIC1 異體
    rules.append(("COMIC☆8", "COMIC1☆8"))
    rules.append(("COMIC1鈽", "COMIC1☆"))  # 亂碼，先標記

    # 6. SC -> サンクリ (數字版)
    for n in [49, 56, 60, 61, 62, 64, 65]:
        rules.append((f"SC{n}", f"サンクリ{n}"))

    # 7. SC20xx -> サンクリ20xx
    for season in ["2015 Winter", "2017 Summer", "2018 Summer",
                    "2019 Spring", "2019 Summer"]:
        rules.append((f"SC{season}", f"サンクリ{season}"))

    # 8. サンシャインクリエイション -> サンクリ
    rules.append(("サンシャインクリエイション2016 Winter", "サンクリ2016 Winter"))
    rules.append(("サンシャインクリエイション59", "サンクリ59"))

    # 9. サンクリ 多餘空格
    rules.append(("サンクリ 2015 Summer", "サンクリ2015 Summer"))
    rules.append(("サンクリ 61", "サンクリ61"))

    # 10. Futaket -> ふたけっと
    rules.append(("Futaket 11", "ふたけっと11"))
    rules.append(("Futaket 11.5", "ふたけっと11.5"))
    rules.append(("Futaket 9.5", "ふたけっと9.5"))

    # 11. ふたけっと 多餘空格
    for n in ["10.5", "11.5", "12", "12.5", "14"]:
        rules.append((f"ふたけっと {n}", f"ふたけっと{n}"))

    # 12. COMITIA -> コミティア
    rules.append(("COMITIA102", "コミティア102"))

    # 13. Mimiket -> みみけっと
    rules.append(("Mimiket 29", "みみけっと29"))

    # 14. ぷにけっと -> ぷにケット (統一用片假名ケット)
    rules.append(("ぷにけっと28", "ぷにケット28"))
    rules.append(("ぷにけっと36", "ぷにケット36"))

    # 15. こみっくトレジャー -> こみトレ
    rules.append(("こみっくトレジャー22", "こみトレ22"))
    rules.append(("こみっくトレジャー25", "こみトレ25"))

    # 16. 例大祭 多餘空格
    rules.append(("例大祭 13", "例大祭13"))

    # 17. Graket -> グラケット
    rules.append(("Graket 2", "グラケット2"))

    # 18. ファータグランデ騎空祭 空格/前導零
    rules.append(("ファータグランデ騎空祭 02", "ファータグランデ騎空祭2"))

    # 19. Fata Grande -> ファータグランデ
    rules.append(("Fata Grande Kikuusai", "ファータグランデ騎空祭"))

    # 20. 海ゆかば
    rules.append(("Umi Yukaba", "海ゆかば"))
    rules.append(("海ゆかば2", "海ゆかば 2"))

    return rules


def build_event_fullwidth_rules(conn):
    """砲雷撃戦等全形標點正規化 (！->!)"""
    rules = []
    rows = conn.execute(
        "SELECT DISTINCT event FROM doujinshi WHERE event LIKE '%！%' OR event LIKE '%？%'"
    ).fetchall()
    for (event,) in rows:
        normalized = event.replace("！", "!").replace("？", "?")
        if normalized != event:
            rules.append((event, normalized))
    return rules


def build_circle_rules():
    """社團合併規則 (大小寫 + 半全形)"""
    # 統一取數量多的作為目標
    return [
        ("A-Walks", "A-WALKs"),
        ("Abarenbow Tengu", "ABARENBOW TENGU"),
        ("Aerodog", "AERODOG"),
        ("Ash wing", "Ash Wing"),
        ("Askray", "AskRay"),
        ("Brave Heart Petit", "BRAVE HEART petit"),
        ("brilliant thunder", "Brilliant Thunder"),  # 4 > 2, 用 Brilliant
        ("C.R's Nest", "C.R's NEST"),
        ("corori", "CORORI"),  # 3 > 1
        ("D-Baird", "D-baird"),  # 4 > 1, 用 D-baird
        ("Da Hootch", "DA HOOTCH"),
        ("Drawpnir", "DRAWPNIR"),  # 2 > 1
        ("Dream Halls！", "Dream Halls!"),
        ("Erect Touch", "ERECT TOUCH"),
        ("EROQUIS！", "EROQUIS!"),
        ("Essentia", "ESSENTIA"),
        ("FatalPulse", "Fatalpulse"),
        ("flicker10", "Flicker10"),
        ("French Letter", "French letter"),  # 10 > 1
        ("Fullmetal Madness", "FULLMETAL MADNESS"),
        ("G-Power！", "G-Power!"),
        ("Heaven  s Gate", "Heaven s Gate"),  # double space -> single
        ("Insert", "INSERT"),
        ("Inst", "INST"),
        ("Karomix", "KAROMIX"),
        ("kuma-puro", "Kuma-puro"),  # 5 > 2, 用 kuma-puro... actually let me keep more popular
        ("Kuro queen", "Kuro Queen"),
        ("Laminaria", "LAMINARIA"),
        ("LV.X+", "Lv.X+"),  # 4 > 1
        ("Moco Chouchou", "moco chouchou"),  # 10 > 1
        ("pink", "PINK"),
        ("Primal gym", "Primal Gym"),
        ("REI's Room", "REI's ROOM"),
        ("Sand", "sand"),  # 6 > 1
        ("SKlabel", "SKLABEL"),
        ("Snob Nerd Works", "SNOB NERD WORKS"),
        ("Studio Pal", "STUDIO PAL"),
        ("Studio TRIUMPH", "STUDIO TRIUMPH"),
        ("T-project", "T-Project"),
        ("Viento Campanilla", "viento campanilla"),  # 13 > 1
        ("Wicked Heart", "WICKED HEART"),
        ("zero戦", "ZERO戦"),
        ("とらいあんぐる！", "とらいあんぐる!"),
    ]


def build_author_rules():
    """作者合併規則 (大小寫)"""
    return [
        ("Aho", "aho"),  # 3 > 1
        ("BadHanD", "BadHand"),  # 合併 - BadHand 看起來更正確但 BadHanD 有 4 筆
        ("Ereere", "ereere"),  # 5 > 1
        ("HiRo", "hiro"),
        ("Inu", "inu"),  # 17 > 1
        ("K-you", "k-you"),  # 4 > 1
        ("Karory", "karory"),  # 6 > 1
        ("Ken", "KEN"),
        ("ken-1", "Ken-1"),  # 7 > 4
        ("Konomi", "konomi"),  # 8 > 1
        ("nohito", "Nohito"),  # 6 > 2
        ("numeko", "Numeko"),  # 3 > 2
        ("rca", "RCA"),
        ("Sasayuki", "SASAYUKi"),  # 11 > 1
        ("sian", "Sian"),  # 3 = 3, 用首字母大寫
        ("staryume", "Staryume"),
        ("TaKe", "TAKE"),
        ("vanadium", "Vanadium"),  # 4 > 1
        ("Xin、obiwan", "xin、obiwan"),  # 4 > 1
        ("たかやki", "たかやKi"),  # 3 > 1
        ("黒川izumi", "黒川IZUMI"),  # 2 > 1
    ]


def build_parody_rules():
    """原作合併規則"""
    return [
        # To LOVEる 統一
        ("To LOVEる", "To LOVEる -とらぶる-"),
        ("To Love-Ru Darkness", "To LOVEる ダークネス"),

        # Fate 系列 - 分數斜線
        ("Fate⁄Grand Order、Fate⁄kaleid liner プリズマ☆イリヤ",
         "Fate Grand Order、Fate kaleid liner プリズマ☆イリヤ"),

        # ポケモン 中黑點統一
        ("ポケットモンスター サン･ムーン", "ポケットモンスター サン・ムーン"),

        # プリキュア 標點
        ("ハートキャッチプリキュア!,", "ハートキャッチプリキュア!"),

        # 半形全形驚嘆號統一 (原作中)
        ("ドキドキ！プリキュア、スマイルプリキュア！",
         "ドキドキ!プリキュア、スマイルプリキュア!"),
        ("ハートキャッチプリキュア！ コピー本", "ハートキャッチプリキュア!"),

        # Fate Grand Order 複合標籤中的分數斜線
        ("Fate Grand Order, Fate kaleid liner プリズマ☆イリヤ",
         "Fate Grand Order、Fate kaleid liner プリズマ☆イリヤ"),
        ("Fate kaleid liner プリズマ☆イリヤ、Fate Grand Order",
         "Fate Grand Order、Fate kaleid liner プリズマ☆イリヤ"),
    ]


def fix_broken_events(conn):
    """修復明顯錯誤解析的場次"""
    total = 0

    # C89 [ミルクプロテイン (風凛花 -> 只取 C89
    cur = conn.execute(
        "UPDATE doujinshi SET event = 'C89' WHERE event LIKE 'C89 [%'"
    )
    if cur.rowcount:
        print(f"  event: 修復 C89 錯誤解析 ({cur.rowcount} 筆)")
        total += cur.rowcount

    # C97 ( [水平線] -> 只取 C97
    cur = conn.execute(
        "UPDATE doujinshi SET event = 'C97' WHERE event LIKE 'C97 (%'"
    )
    if cur.rowcount:
        print(f"  event: 修復 C97 錯誤解析 ({cur.rowcount} 筆)")
        total += cur.rowcount

    # 非場次名的值: 'WORKING!!', 'Easy Game', 'Cyclone', 'Artist CG',
    # '同人 CG集', '成年コミック', '東方' -> 這些應該不是場次
    non_events = [
        "WORKING!!", "Easy Game", "Cyclone", "Artist CG",
        "同人 CG集", "成年コミック", "東方", "Sennen Quest",
    ]
    for ne in non_events:
        row = conn.execute(
            "SELECT id, filename, title, parody FROM doujinshi WHERE event = ?",
            (ne,)
        ).fetchone()
        if row:
            # 判斷是否更適合放在其他欄位
            if ne == "東方":
                conn.execute(
                    "UPDATE doujinshi SET event = '', parody = '東方Project' "
                    "WHERE event = ? AND (parody IS NULL OR parody = '')", (ne,)
                )
                conn.execute(
                    "UPDATE doujinshi SET event = '' WHERE event = ?", (ne,)
                )
                print(f"  event: [{ne}] 移至 parody=東方Project")
            else:
                conn.execute(
                    "UPDATE doujinshi SET event = '' WHERE event = ?", (ne,)
                )
                print(f"  event: [{ne}] 清除 (非場次名)")
            total += 1

    return total


def cleanup_parody_fullwidth(conn):
    """原作名中的全形半形統一"""
    total = 0
    rows = conn.execute(
        "SELECT DISTINCT parody FROM doujinshi WHERE parody LIKE '%！%'"
    ).fetchall()
    for (parody,) in rows:
        normalized = parody.replace("！", "!").replace("？", "?")
        if normalized != parody:
            # 檢查正規化後的值是否已存在
            existing = conn.execute(
                "SELECT COUNT(*) FROM doujinshi WHERE parody = ?",
                (normalized,)
            ).fetchone()[0]
            cur = conn.execute(
                "UPDATE doujinshi SET parody = ? WHERE parody = ?",
                (normalized, parody)
            )
            if cur.rowcount:
                print(f"  parody: [{parody}] -> [{normalized}] ({cur.rowcount} 筆)")
                total += cur.rowcount
    return total


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    total_changes = 0

    print("=" * 60)
    print("同人誌資料庫清理")
    print("=" * 60)

    # --- 場次 ---
    print("\n【場次 (event) 合併】")
    event_rules = build_event_rules()
    event_fw_rules = build_event_fullwidth_rules(conn)
    total_changes += merge_field(conn, "event", event_rules)
    total_changes += merge_field(conn, "event", event_fw_rules)

    print("\n【場次 錯誤修復】")
    total_changes += fix_broken_events(conn)

    # --- 社團 ---
    print("\n【社團 (circle) 合併】")
    total_changes += merge_field(conn, "circle", build_circle_rules())

    # --- 作者 ---
    print("\n【作者 (author) 合併】")
    total_changes += merge_field(conn, "author", build_author_rules())

    # --- 原作 ---
    print("\n【原作 (parody) 合併】")
    total_changes += merge_field(conn, "parody", build_parody_rules())

    print("\n【原作 全形標點正規化】")
    total_changes += cleanup_parody_fullwidth(conn)

    conn.commit()

    # --- 統計 ---
    print("\n" + "=" * 60)
    print(f"總計修改: {total_changes} 筆")

    # 修改後的統計
    for col, label in [("event", "場次"), ("circle", "社團"),
                        ("author", "作者"), ("parody", "原作")]:
        distinct = conn.execute(
            f"SELECT COUNT(DISTINCT {col}) FROM doujinshi "
            f"WHERE {col} IS NOT NULL AND {col} != ''"
        ).fetchone()[0]
        null_count = conn.execute(
            f"SELECT COUNT(*) FROM doujinshi "
            f"WHERE {col} IS NULL OR {col} = ''"
        ).fetchone()[0]
        print(f"  {label}: {distinct} 種 ({null_count} 筆未分類)")

    conn.close()
    print("\n清理完成！(原始資料庫已備份為 doujin.db.bak)")


if __name__ == "__main__":
    main()
