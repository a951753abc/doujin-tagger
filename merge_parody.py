"""原作標籤整合腳本

兩階段合併：
1. 自動正規化合併（空格/標點/大小寫差異）
2. 手動語義合併（英日對照、縮寫、系列整合）
"""

import sqlite3
import re
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent / "doujin.db"


def normalize(s: str) -> str:
    """正規化字串用於比對（不改變原始值）"""
    s = s.lower().strip()
    # Unicode 斜線統一
    s = s.replace("\u2044", "/").replace("\uff0f", "/")
    # 全形→半形標點
    s = s.replace("\uff01", "!").replace("\uff1a", ":").replace("\uff1f", "?")
    s = s.replace("\uff06", "&").replace("\uff0c", ",")
    # 移除裝飾符號
    s = s.replace("☆", "").replace("★", "").replace("♡", "").replace("♥", "")
    # 移除空格/連字號/中間點
    s = re.sub(r"[\s\-\u00b7\u30fb\u3000\u2003]+", "", s)
    return s


# ── 手動語義合併對照表 ──
# canonical_name → [variants]
SEMANTIC_MERGES = {
    # Fate Grand Order
    "Fate Grand Order": [
        "FateGrand Order", "Fate-Grand Order", "Fate GrandOrder",
        "FateGrand order", "Fate⁄Grand Order", "Fate／Grand Order",
        "FGO", "fgo",
    ],
    # 艦これ
    "艦隊これくしょん -艦これ-": [
        "艦隊これくしょん-艦これ-", "艦隊これくしょん  -艦これ-",
        "艦隊これくしょん --艦これ", "艦隊これくしょん -艦これ",
        "艦隊これくしょん-艦これ -", "艦隊これくしょん",
        "艦これ", "Kantai Collection -KanColle-",
        "Kantai Collection", "Kantai Collection -Kancolle-",
        "kantai collection -Kan kore-",
        "隊これくしょん-艦これ-",  # typo
    ],
    # 東方
    "東方Project": [
        "東方 Project", "東方project", "東方",
        "Touhou Project",
    ],
    # グラブル
    "グランブルーファンタジー": [
        "グランブルー ファンタジー", "Granblue Fantasy",
        "ルグランブルーファンタジー",  # typo
    ],
    # アイマス シンデレラ
    "アイドルマスター シンデレラガールズ": [
        "アイドルマスターシンデレラガールズ",
        "THE IDOLM@STER CINDERELLA GIRLS",
        "THE IDOLM STER CINDERELLA GIRLS",
        "THE IDOLMSTER CINDERELLA GIRLS",
        "Idolm@ster Cinderella Girls",
        "アイドルマスタ シンデレラガールズー",
    ],
    # アイマス シャニマス
    "アイドルマスター シャイニーカラーズ": [
        "アイドルマスターシャイニーカラーズ",
        "THE iDOLM STER  Shiny Colors",
        "THE iDOLM@STER- Shiny Colors",
        "THE iDOLMSTER  Shiny Colors",
    ],
    # アイマス 本家
    "アイドルマスター": [
        "THE IDOLM@STER", "THE iDOLM@STER", "THE iDOLM@STER",
        "アイマス", "IM@S", "I@M", "PROJECT IM@S",
    ],
    # アイマス ミリオン
    "アイドルマスター ミリオンライブ!": [
        "アイドルマスターミリオンライブ!",
    ],
    # 学マス
    "学園アイドルマスター": [],
    # ソードアート・オンライン
    "ソードアート・オンライン": [
        "ソードアート·オンライン", "ソードアート · オンライン",
        "ソードアートオンライン", "Sword Art Online",
    ],
    # ラブライブ!
    "ラブライブ!": [
        "ラブライブ！", "ラブライブ", "Love Live!", "Love Live",
    ],
    # ラブライブ! サンシャイン!!
    "ラブライブ! サンシャイン!!": [
        "ラブライブ!サンシャイン!!",
    ],
    # Fate/kaleid liner プリズマ☆イリヤ
    "Fate/kaleid liner プリズマ☆イリヤ": [
        "Fate kaleid liner プリズマ☆イリヤ",
        "Fatekaleid liner プリズマ☆イリヤ",
        "Fate／kaleid liner プリズマ☆イリヤ",
        "Fate⁄kaleid liner プリズマ☆イリヤ",
        "Fate kaleid liner Prisma Illya",
    ],
    # Fate/stay night
    "Fate/stay night": [
        "Fate stay night", "Fatestay night", "Fate stay Night",
        "Fate／stay night", "Fate／stay Night",
        "フェイト ステイナイト",
    ],
    # Fate/Apocrypha
    "Fate/Apocrypha": [
        "Fate Apocrypha", "FateApocrypha", "Fate／Apocrypha",
    ],
    # Fate/EXTRA
    "Fate/EXTRA": [
        "Fate EXTRA", "FateEXTRA", "Fate Extra", "FateExtra",
        "Fate⁄EXTRA", "Fate⁄Extra", "Fate／EXTRA",
    ],
    # Fate/EXTRA CCC
    "Fate/EXTRA CCC": [
        "Fate EXTRA CCC", "FateEXTRA CCC", "Fate／EXTRA CCC",
    ],
    # Fate/EXTELLA
    "Fate/EXTELLA": [
        "Fate EXTELLA", "FateEXTELLA",
    ],
    # Fate/Zero
    "Fate/Zero": [
        "Fate Zero", "FateZero", "フェイト ゼロ",
    ],
    # けいおん!
    "けいおん!": [
        "けいおん！", "けいおん", "けーおん",
        "K-ON!", "K-On!", "K-on!", "K-ON", "k-on!",
    ],
    # けいおん!!（二期）保持不變，但統一全形
    "けいおん!!": [],
    # 魔法少女まどか☆マギカ
    "魔法少女まどか☆マギカ": [
        "魔法少女まどかマギカ", "まどかマギカ",
        "Puella Magi MadokaâMagica",
    ],
    # ブルーアーカイブ
    "ブルーアーカイブ": [
        "ブルーアーカイブ -Blue Archive-",
        "ブルーアーガイブ",  # typo
    ],
    # アズールレーン
    "アズールレーン": ["Azur Lane"],
    # この素晴らしい世界に祝福を!
    "この素晴らしい世界に祝福を!": [
        "この素晴らしい世界に祝福を！",
        "こ素晴らしい世界に祝福を!",  # typo
        "Kono Subarashii Sekai ni Syukufuku o!",
        "Kono Subarashii Sekai ni Shukufuku o!",
        "Kono Subarashii Sekai ni Shukufuku wo!",
    ],
    # To LOVEる -とらぶる-
    "To LOVEる -とらぶる-": [
        "ToLOVEる-とらぶる-", "ToLOVEる -とらぶる-",
    ],
    # To LOVEる ダークネス
    "To LOVEる ダークネス": [
        "ToLOVEる ダークネス", "To LOVEる ダークネス",
        "ToLoveる ダークネス", "ToLOVEダークネス",
        "To LOVE-Ru Darkness", "To LOVEる -とらぶる- ダークネス",
    ],
    # To LOVEる（無印、短縮形）
    "To LOVEる": [
        "ToLOVEる", "ToLoveる", "To LOVE-Ru", "ToLoveRu",
    ],
    # 咲 -Saki-
    "咲 -Saki-": [
        "咲-Saki-", "咲-saki", "Saki",
    ],
    # プリンセスコネクト!Re:Dive
    "プリンセスコネクト!Re:Dive": [
        "プリンセスコネクト!Re：Dive",
        "プリンセスコネクト! Re：Dive",
        "プリンセスコネクト!Re Dive",
        "プリンセスコネクト!ReDive",
        "プリンセスコネクト！ReDive",
        "プリンセスコネクト!ReDive!",
        "プリンセスコネクト!",
    ],
    # Re:ゼロから始める異世界生活
    "Re:ゼロから始める異世界生活": [
        "Re：ゼロから始める異世界生活",
        "Reゼロから始める異世界生活",
        "Re ゼロから始める異世界生活",
        "Re-Zero kara Hajimeru Isekai Seikatsu",
        "Re-Zero Kara Hajimeru Isekai Seikatsu",
    ],
    # インフィニット・ストラトス
    "インフィニット・ストラトス": [
        "インフィニット ストラトス", "インフィニットストラトス",
        "インフィニット ストラト",  # truncated
        "インフィニットストラトス＞",  # stray bracket
        "インフィニット・ストラトス＞",
        "Infinite Stratos",
    ],
    # IS＜インフィニット・ストラトス＞
    "IS＜インフィニット・ストラトス＞": [
        "IS＜インフィニット ストラトス＞",
        "IS -インフィニット・ストラトス-",
        "IS",
    ],
    # ポケットモンスター
    "ポケットモンスター": ["ポケモン", "Pokemon", "Pokémon"],
    # ポケットモンスター サン・ムーン
    "ポケットモンスター サン・ムーン": [
        "ポケットモンスターサン・ムーン",
        "Pokémon Sun and Moon",
    ],
    # ハヤテのごとく!
    "ハヤテのごとく!": [
        "ハヤテのごとく！", "ハヤテのごとく",
        "ハヤテ",
    ],
    # SSSS.GRIDMAN
    "SSSS.GRIDMAN": ["SSSS.Gridman", "SSSS Gridman"],
    # はたらく魔王さま!
    "はたらく魔王さま!": [
        "はたらく魔王さま！",
        "Hataraku Maou-sama!",
    ],
    # ダンジョンに出会いを求めるのは間違っているだろうか
    "ダンジョンに出会いを求めるのは間違っているだろうか": [
        "ダンまち", "ダンマチ",
        "Dungeon ni Deai o Motomeru no wa Machigatteiru Darou ka",
        "Dungeon ni Deai wo Motomeru no wa Machigatteiru Darou ka",
    ],
    # 僕は友達が少ない
    "僕は友達が少ない": ["Boku wa Tomodachi ga Sukunai"],
    # 美少女戦士セーラームーン
    "美少女戦士セーラームーン": [
        "セーラームーン", "セラムン",
        "Bishoujo Senshi Sailor Moon", "Sailor+Moon",
        "美少女戦士セーラームーンシリーズ",
    ],
    # Steins;Gate
    "Steins;Gate": [
        "Steins Gate", "Steins；Gate",
        "シュタインズゲート", "シュタインズ・ゲート", "シュタインズ ゲート",
    ],
    # beatmania IIDX
    "beatmania IIDX": ["beatmaniaIIDX", "beatmaniaⅡDX", "ビートマニア"],
    # パズル&ドラゴンズ
    "パズル&ドラゴンズ": ["パズル＆ドラゴンズ", "Puzzle & Dragons"],
    # WORKING!!
    "WORKING!!": ["WORKING!", "Working"],
    # ドキドキ!プリキュア
    "ドキドキ!プリキュア": [
        "ドキドキ！プリキュア", "ドキドキ! プリキュア",
        "ドキドキ！プリキュア", "(ドキドキ！プリキュア",
        "Doki Doki Precure", "Dokidoki! Precure",
    ],
    # スマイルプリキュア!
    "スマイルプリキュア!": [
        "スマイルプリキュア！", "スマイルプリキュア",
        "Smile Precure!",
    ],
    # ハピネスチャージプリキュア!
    "ハピネスチャージプリキュア!": [
        "ハピネスチャージプリキュア！",
        "Happiness Charge Precure!",
    ],
    # ハートキャッチプリキュア!
    "ハートキャッチプリキュア!": [
        "ハートキャッチプリキュア！", "ハートキャッチプリキュア",
        "Heartcatch Precure",
    ],
    # Go!プリンセスプリキュア
    "Go!プリンセスプリキュア": [
        "Go! プリンセスプリキュア", "GO!プリンセスプリキュア",
    ],
    # 魔法つかいプリキュア!
    "魔法つかいプリキュア!": [
        "魔法つかいプリキュア！",
        "魔法使いプリキュア!", "魔法使いプリキュア！",
        "Mahou Tsukai Precure!",
    ],
    # HUGっと!プリキュア
    "HUGっと!プリキュア": [
        "HUGっと! プリキュア", "Hugと!プリキュア",
    ],
    # 超次元ゲイム ネプテューヌ
    "超次元ゲイム ネプテューヌ": [
        "超次元ゲイムネプテューヌ",
        "Hyperdimension Neptunia",
    ],
    # 中二病でも恋がしたい!
    "中二病でも恋がしたい!": [
        "中二病でも恋がしたい！",
        "Chuunibyou Demo Koi ga Shitai!",
    ],
    # あにゃまる探偵 キルミンずぅ
    "あにゃまる探偵 キルミンずぅ": ["あにゃまる探偵キルミンずぅ"],
    # ToHeart2
    "ToHeart2": ["To Heart 2", "ToHeart 2", "TH2"],
    # ToHeart
    "ToHeart": ["To Heart"],
    # ゼノブレイド2
    "ゼノブレイド2": ["ゼノブレイド 2", "Xenoblade Chronicles 2"],
    # 聖剣伝説3
    "聖剣伝説3": ["聖剣伝説 3", "聖剣3"],
    # モンスターハンター
    "モンスターハンター": ["モンハン", "MH"],
    # ドラゴンクエスト
    "ドラゴンクエスト": ["ドラクエ", "Dragon Quest", "DQ"],
    # ドラゴンクエスト3
    "ドラゴンクエスト3": [
        "ドラゴンクエスト 3", "ドラゴンクエストIII", "ドラクエ3",
        "DQ3", "Dragon Quest 3",
    ],
    # ドラゴンクエスト4
    "ドラゴンクエスト4": ["ドラゴンクエストIV", "ドラゴンクエスト IV"],
    # ドラゴンクエスト5
    "ドラゴンクエスト5": [
        "ドラゴンクエストV", "ドラゴンクエスト V", "ドラゴンクエストⅤ",
        "DQ5", "Dragon Quest V",
    ],
    # ドラゴンクエスト6
    "ドラゴンクエスト6": ["DQ6"],
    # ドラゴンクエスト7
    "ドラゴンクエスト7": ["ドラゴンクエストVII"],
    # ドラゴンクエスト9
    "ドラゴンクエスト9": ["ドラゴンクエストIX", "ドラクエ9"],
    # ドラゴンクエスト8
    "ドラゴンクエスト8": ["DQ8"],
    # ガールズ&パンツァー
    "ガールズ&パンツァー": [],
    # 俺の妹がこんなに可愛いわけがない
    "俺の妹がこんなに可愛いわけがない": [
        "俺の妹がこんなにかわいいわけがない",
        "Ore no Imouto ga Konna ni Kawaii Wake ga Nai",
    ],
    # エロマンガ先生
    "エロマンガ先生": ["Eromanga Sensei"],
    # コードギアス 反逆のルルーシュ
    "コードギアス 反逆のルルーシュ": ["コードギアス", "Code Geass"],
    # 閃乱カグラ
    "閃乱カグラ": ["Senran Kagura"],
    # ダンガンロンパ
    "ダンガンロンパ": ["ダンガンロンパ 希望の学園と絶望の高校生"],
    # スーパーダンガンロンパ2
    "スーパーダンガンロンパ2": ["ダンガンロンパ2", "Super Danganronpa 2"],
    # 遊☆戯☆王
    "遊☆戯☆王": ["遊戯王", "Yu-Gi-Oh!", "遊☆戯☆王!"],
    # ストライクウィッチーズ
    "ストライクウィッチーズ": ["Strike Witches"],
    # ペルソナ4
    "ペルソナ4": ["Persona 4"],
    # アクセル・ワールド
    "アクセル・ワールド": ["アクセルワールド"],
    # ドラゴンボール
    "ドラゴンボール": ["Dragon Ball"],
    # BLAZBLUE
    "BLAZBLUE": ["BLAZE-BLUE", "ブレイブルー"],
    # ギルティギア
    "ギルティギア": ["Guilty Gear", "GUILTY GEARシリーズ"],
    # ギルティギア Xrd
    "ギルティギア Xrd": [],
    # ファイナルファンタジー
    "ファイナルファンタジー": ["FF"],
    # ファイナルファンタジーVII
    "ファイナルファンタジーVII": ["FF7"],
    # ファイナルファンタジーIV
    "ファイナルファンタジーIV": ["ファイナルファンタジー4", "FF4"],
    # 花咲くいろは
    "花咲くいろは": [],
    # 世界征服～謀略のズヴィズダー～
    "世界征服～謀略のズヴィズダー～": [
        "世界征服～謀略のズヴィズダー",
        "世界征服 ～謀略のズヴィズダー",
        "世界征服〜謀略のズヴィズダー〜",
        "Sekai Seifuku ~Bouryaku no Zvezda~",
    ],
    # 甘城ブリリアントパーク
    "甘城ブリリアントパーク": [
        "天城ブリリアントパーク",  # typo
        "Amagi Brilliant Park",
    ],
    # TIGER & BUNNY
    "TIGER & BUNNY": ["TIGER&BUNNY"],
    # Angel Beats!
    "Angel Beats!": ["Angel Beat!", "エンジェルビーツ!", "エンジェルビーツ"],
    # 月曜日のたわわ
    "月曜日のたわわ": ["Getsuyoubi no Tawawa"],
    # りゅうおうのおしごと!
    "りゅうおうのおしごと!": ["Ryuuou no Oshigoto!"],
    # あの日見た花の名前を僕達はまだ知らない。
    "あの日見た花の名前を僕達はまだ知らない。": [
        "あの日見た花の名前を僕達はまだ知らない",
        "あの花",
    ],
    # 魔法少女リリカルなのは
    "魔法少女リリカルなのは": [
        "なのは", "なのは1期",
        "Mahou Shoujo Lyrical Nanoha",
        "魔法少女リリカルなのはシリーズ",
    ],
    # 五等分の花嫁
    "五等分の花嫁": ["Gotoubun no Hanayome"],
    # ご注文はうさぎですか？
    "ご注文はうさぎですか？": [],
    # ぼっち・ざ・ろっく!
    "ぼっち・ざ・ろっく!": [],
    # 境界線上のホライゾン
    "境界線上のホライゾン": [
        "境界線上のホライゾン",  # there's a duplicate with different space
        "Kyoukai Senjou no Horizon",
    ],
    # 探偵オペラ ミルキィホームズ
    "探偵オペラ ミルキィホームズ": [
        "探偵オペラ\u3000ミルキィホームズ",  # full-width space
        "探偵オペラミルキィホームズ",
    ],
    # 這いよれ! ニャル子さん
    "這いよれ! ニャル子さん": [
        "這いよれ！ニャル子さん",
        "Haiyore! Nyaruko-san",
    ],
    # ロウきゅーぶ!
    "ロウきゅーぶ!": ["ロウきゅーぶ！"],
    # バカとテストと召喚獣
    "バカとテストと召喚獣": ["Baka to Test to Shoukanjuu"],
    # よつばと!
    "よつばと!": ["よつばと！"],
    # らき☆すた
    "らき☆すた": ["らきすた"],
    # 進撃の巨人
    "進撃の巨人": [],
    # ワンパンマン
    "ワンパンマン": ["One Punch Man"],
    # 小林さんちのメイドラゴン
    "小林さんちのメイドラゴン": [],
    # 鬼滅の刃
    "鬼滅の刃": [],
    # 原神
    "原神": [],
    # VOCALOID
    "VOCALOID": ["ボーカロイド"],
    # 初音ミク → keep separate from VOCALOID
    # まよチキ!
    "まよチキ!": ["まよチキ！", "Mayo Chiki!"],
    # おしえて! ギャル子ちゃん
    "おしえて! ギャル子ちゃん": ["おしえて!ギャル子ちゃん"],
    # バクマン
    "バクマン。": ["バクマン"],
    # セイバーマリオネット
    "セイバーマリオネット": ["セイバーマリオネットJ", "セイバーマリオネットJ to X"],
    # ジュエルペット てぃんくる☆
    "ジュエルペット てぃんくる☆": ["ジュエルペットてぃんくる☆"],
    # 真剣で私に恋しなさい!
    "真剣で私に恋しなさい!": ["真剣で私に恋しなさい！"],
    # 恋姫無双
    "恋姫無双": ["真・恋姫†無双", "真・恋姫無双", "真・恋姫＋無双"],
    # フルメタル・パニック!
    "フルメタル・パニック!": ["フルメタル・パニック！", "フルメタルパニック"],
    # にゃんこい!
    "にゃんこい!": ["にゃんこい！"],
    # ハイスクールD×D
    "ハイスクールD×D": ["ハイスクールDxD", "Highschool DxD"],
    # とらドラ!
    "とらドラ!": ["とらドラ"],
    # 日本語/English equivalents for common series
    "ドラゴンクエストXI": [],
    "NEW GAME!": [],
    "ラグナロクオンライン": ["Ragnarok Online"],
    "アイカツ!": ["アイカツ！", "アイカツ", "Aikatsu"],
    "DOG DAYS": ["ドッグデイズ"],
    "クイズマジックアカデミー": ["QUIZ MAGIC ACADEMY", "QMA"],
    "デート・ア・ライブ": ["デート·ア·ライブ", "Date A Live"],
    "ファイアーエムブレム": [],
    "侵略!イカ娘": ["侵略！イカ娘", "イカ娘"],
    "ロッテのおもちゃ!": ["ロッテのおもちゃ！"],
    "食戟のソーマ": [],
    "生徒会役員共": [],
    "ニセコイ": [],
    "ストライク・ザ・ブラッド": ["Strike The Blood"],
    "SHOW BY ROCK!!": [],
    "スイートプリキュア♪": ["スイートプリキュア"],
    "だから僕は、Hができない。": [],
    "マクロスF": ["マクロスフロンティア", "マクロスF (フロンティア"],
    "崩壊スターレイル": ["崩壊：スターレイル"],
    "ロックマン": [],  # ロックマンエグゼ は別シリーズ、合併しない
    "ヘタリア": [],
    "カノン": ["KANON", "Kanon"],
    "真・三國無双": ["真 三國無双", "真・三國無双シリーズ"],
    # Keep these separate:
    "Fate": [],  # generic Fate
    "オリジナル": ["Original", "Various"],
    "よろず": ["よろずイラスト"],  # misc / multi-series
}


def build_merge_map(parody_counts: dict) -> dict:
    """
    建立 {variant: canonical} 對照表

    parody_counts: {parody_name: count}
    """
    merge_map = {}

    # ── 階段一：手動語義合併 ──
    for canonical, variants in SEMANTIC_MERGES.items():
        for v in variants:
            if v in parody_counts and v != canonical:
                merge_map[v] = canonical

    # ── 階段二：自動正規化合併（尚未被手動處理的） ──
    norm_groups = defaultdict(list)
    for parody, cnt in parody_counts.items():
        if parody not in merge_map:  # 還沒被手動映射
            key = normalize(parody)
            norm_groups[key].append((parody, cnt))

    for key, entries in norm_groups.items():
        if len(entries) <= 1:
            continue
        # 選最高數量的作為 canonical
        entries.sort(key=lambda x: -x[1])
        canonical = entries[0][0]
        for parody, cnt in entries[1:]:
            if parody != canonical:
                merge_map[parody] = canonical

    return merge_map


def apply_merges(db_path: Path, merge_map: dict, dry_run: bool = False):
    """套用合併到資料庫"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    total_updated = 0
    merge_summary = defaultdict(lambda: {"variants": [], "count": 0})

    for old_val, new_val in sorted(merge_map.items(), key=lambda x: x[1]):
        cur = conn.execute(
            "SELECT COUNT(*) FROM doujinshi WHERE parody = ?", (old_val,)
        )
        count = cur.fetchone()[0]
        if count == 0:
            continue

        merge_summary[new_val]["variants"].append(f"{old_val} ({count})")
        merge_summary[new_val]["count"] += count

        if not dry_run:
            conn.execute(
                "UPDATE doujinshi SET parody = ?, updated_at = CURRENT_TIMESTAMP WHERE parody = ?",
                (new_val, old_val),
            )
            total_updated += count

    if not dry_run:
        conn.commit()
    conn.close()

    return total_updated, merge_summary


def main():
    import sys

    dry_run = "--dry-run" in sys.argv

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(
        "SELECT parody, COUNT(*) FROM doujinshi WHERE parody IS NOT NULL AND parody != '' GROUP BY parody"
    )
    parody_counts = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()

    merge_map = build_merge_map(parody_counts)

    if not merge_map:
        print("沒有需要合併的項目。")
        return

    mode = "【預覽模式】" if dry_run else "【執行模式】"
    print(f"\n{mode} 原作標籤整合")
    print(f"{'=' * 60}")

    total_updated, summary = apply_merges(DB_PATH, merge_map, dry_run=dry_run)

    for canonical in sorted(summary, key=lambda k: summary[k]["count"], reverse=True):
        info = summary[canonical]
        print(f"\n→ {canonical} (+{info['count']})")
        for v in info["variants"]:
            print(f"    ← {v}")

    print(f"\n{'=' * 60}")
    print(f"合併群組數: {len(summary)}")
    print(f"受影響筆數: {total_updated}")

    if dry_run:
        print("\n（這是預覽模式，尚未修改資料庫。移除 --dry-run 以執行。）")

    # 合併後統計
    if not dry_run:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.execute(
            "SELECT COUNT(DISTINCT parody) FROM doujinshi WHERE parody IS NOT NULL AND parody != ''"
        )
        remaining = cur.fetchone()[0]
        conn.close()
        print(f"合併後剩餘原作數: {remaining}")


if __name__ == "__main__":
    main()
