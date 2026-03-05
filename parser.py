"""同人誌檔名解析模組"""

import re
from dataclasses import dataclass, asdict
from typing import Optional
from urllib.parse import unquote


@dataclass(frozen=True)
class ParsedDoujinshi:
    event: Optional[str] = None       # 場次 (C106, COMIC1☆8, etc.)
    circle: Optional[str] = None      # 社團名
    author: Optional[str] = None      # 作者名
    title: Optional[str] = None       # 作品標題
    parody: Optional[str] = None      # 原作作品名
    is_dl: bool = False               # DL版
    detected_category: Optional[str] = None  # 從檔名偵測到的分類

    def to_dict(self):
        return asdict(self)


# 已知場次前綴 pattern
EVENT_PATTERN = re.compile(
    r'^\('
    r'('
    r'C\d+'                           # C77, C100, C106
    r'|AC\d+'                         # AC2, AC3 (エアコミケ)
    r'|COMIC\d+'                      # COMIC06, COMIC25
    r'|COMIC1[☆★]\d+'               # COMIC1☆8, COMIC1☆15
    r'|COMITIA\d+'                    # COMITIA102
    r'|SC\d+'                         # SC57, SC65 (サンクリ)
    r'|GW'                            # GW
    r'|[^\)]{1,50}'                   # 其他場次名 (こみっくトレジャー22, Sanctum Archive chapter.4)
    r')'
    r'\)\s*'
)

# 要跳過的 tag pattern（出現在檔名中但非 metadata）
SKIP_TAGS = re.compile(
    r'\[(DL版|Digital|Chinese|英訳|韓国翻訳|caso|omake付|別スキャン)[^\]]*\]',
    re.IGNORECASE
)

# 前綴垃圾 pattern
PREFIX_JUNK = re.compile(r'^\[[^\]]*@[^\]]*\]\s*')  # [firelee@2DJGAME]

# 商業誌分類前綴（這些不是場次，而是分類標記）
COMMERCIAL_CATEGORIES = {
    '成年コミック': '成年コミック',
    '官能小説・エロライトノベル': '官能小説',
    '官能小説': '官能小説',
    'エロライトノベル': '官能小説',
    'エロ漫画': '成年コミック',
    '一般コミック': '一般コミック',
    'アダルトコミック': '成年コミック',
}

# 商業誌前綴 pattern
COMMERCIAL_PATTERN = re.compile(
    r'^\('
    r'(' + '|'.join(re.escape(k) for k in COMMERCIAL_CATEGORIES) + r')'
    r'\)\s*'
)

# 原作名正規化映射（變體 → 正式名稱）
PARODY_ALIASES = {
    '東方': '東方Project',
    'Original': 'オリジナル',
    'original': 'オリジナル',
    'Various': 'よろず',
    # English/Romaji → Japanese
    'Bakemonogatari': '化物語',
    'Bakemonogari': '化物語',
    'Rozen Maiden': 'ローゼンメイデン',
    'Saki': '咲 -Saki-',
    'Highschool DxD': 'ハイスクールD×D',
    'Dead Or Alive': 'デッド・オア・アライブ',
    'Toaru Majutsu no Index': 'とある魔術の禁書目録',
    'Smile Precure': 'スマイルプリキュア!',
    'Suite PreCure': 'スイートプリキュア',
    'Dokidoki! Precure': 'ドキドキ!プリキュア',
    'Puella Magi Madoka Magica': '魔法少女まどか☆マギカ',
    'Mahou Shoujo Lyrical Nanoha': '魔法少女リリカルなのは',
    'Alice in Wonderland': '不思議の国のアリス',
    'Aquarion Evol': 'アクエリオンEVOL',
    'Tamako Market': 'たまこまーけっと',
    'Ragnarok Online': 'ラグナロクオンライン',
    'Infinite Stratos': 'インフィニット・ストラトス',
    'Blue Archive': 'ブルーアーカイブ',
    'Kemono Friends': 'けものフレンズ',
    'Katanagatari': '刀語',
    'Shadowverse': 'シャドウバース',
    "Queen's Blade": 'クイーンズブレイド',
    'Etrian Odyssey': '世界樹の迷宮',
    'DATE A LIVE': 'デート・ア・ライブ',
    'Dynasty Warriors': '真・三國無双',
    'Love Plus': 'ラブプラス',
    # Japanese variant normalization
    'ToLOVEる': 'To LOVEる -とらぶる-',
    'とらぶる': 'To LOVEる -とらぶる-',
    'To LOVE-Ru Darkness': 'To LOVEる ダークネス',
    'IS': 'インフィニット・ストラトス',
    'IS＜インフィニット・ストラトス＞': 'インフィニット・ストラトス',
    'セーラームーン': '美少女戦士セーラームーン',
    'ポケモン': 'ポケットモンスター',
    'モバマス': 'アイドルマスター シンデレラガールズ',
    'ネギま': '魔法先生ネギま!',
    'クラナド': 'CLANNAD',
    'エヴァンゲリオン': '新世紀エヴァンゲリオン',
    'ドラクエ': 'ドラゴンクエスト',
    'ボーカロイド': 'VOCALOID',
    # Fate series normalization
    'Fate Grand Order': 'Fate/Grand Order',
    'Fate／Grand Order': 'Fate/Grand Order',
    'Fate／Zero': 'Fate/Zero',
    'Fate／セイバー': 'Fate/stay night',
    # SAO variants
    'Sword Art Online': 'ソードアート・オンライン',
    'SAO': 'ソードアート・オンライン',
    'ソードアート · オンライン': 'ソードアート・オンライン',
    'ソードアート オンライン': 'ソードアート・オンライン',
    # More English/Romaji → Japanese
    'Toaru Kagaku no Railgun': 'とある科学の超電磁砲',
    'Pokemon': 'ポケットモンスター',
    'Accel World': 'アクセル・ワールド',
    'アクセルワールド': 'アクセル・ワールド',
    # Boundary Horizon variants
    '境界線上のホライズン': '境界線上のホライゾン',
    # IS variants
    'IS＜インフィニットストラトス＞': 'インフィニット・ストラトス',
    # Precure variants (fullwidth ！)
    'スマイルプリキュア！': 'スマイルプリキュア!',
    'ハートキャッチプリキュア！': 'ハートキャッチプリキュア!',
    'ハートキャッチプリキュア': 'ハートキャッチプリキュア!',
    # Idolmaster
    'アイマス': 'アイドルマスター',
    # Typos / encoding issues
    '月姬': '月姫',
    '夜ノヤッーマン': '夜ノヤッターマン',
    '俺の がこんなに可愛いわけがない': '俺の妹がこんなに可愛いわけがない',
    '天色＊アイルノーツ': '天色アイルノーツ',
    'まりあ ほりっく': 'まりあ†ほりっく',
    'さよなら 絶望先生': 'さよなら絶望先生',
    # Abbreviations / English → Japanese
    'AW': 'アクセル・ワールド',
    'ときメモ': 'ときめきメモリアル',
    'ときメモ4': 'ときめきメモリアル4',
    'マクロスFRONTIER': 'マクロスF',
    'ゴッドイーター': 'GOD EATER',
    'サムライスピリッツ': '侍魂',
    'サムライスピリッツ侍魂': '侍魂',
    'Zettai+Karen+Children': '絶対可憐チルドレン',
    'Kiratto Pri Chan': 'キラッとプリ☆チャン',
    'Super Mario Bros.': 'スーパーマリオブラザーズ',
    # Series name normalization
    'アイドルマスターシリーズ': 'アイドルマスター',
    'プリキュアシリーズ': 'プリキュア',
    'ラブライブ! School idol project': 'ラブライブ!',
    'ラブライブ! シリーズ': 'ラブライブ!',
    '聖剣伝説シリーズ': '聖剣伝説',
    'テイルズオブ シリーズ': 'テイルズシリーズ',
    # Strip appended character names
    'けんぷファー ナツル 雫': 'けんぷファー',
    'にゃんこい! 加奈子': 'にゃんこい!',
    'ひだまりスケッチ／ゆの': 'ひだまりスケッチ',
    'オリジナル , ふたなり': 'オリジナル',
    'オリジナル,ショタ': 'オリジナル',
    # Long/short name normalization
    'TERA': 'TERA The Exiled Realm of Arborea',
    'ガンダムSEED DESTINY': '機動戦士ガンダムSEED DESTINY',
    '機動戦士ガンダムAGE': 'ガンダムAGE',
    'ペルソナ3P': 'ペルソナ3',
    'ペルソナ3ポータブル': 'ペルソナ3',
    '神羅万象': '神羅万象チョコ',
    'ダイの大冒険': 'ドラゴンクエスト ダイの大冒険',
    'ドラゴンクエスト III そして伝説へ…': 'ドラゴンクエスト3',
    'ドラゴンクエストIII': 'ドラゴンクエスト3',
    'New スーパーマリオブラザーズ U デラックス': 'スーパーマリオブラザーズ',
    'ドリームクラブZERO': 'ドリームクラブ',
    'クロスウォーズ': 'デジモンクロスウォーズ',
    '超昂大戦': '超昂大戦エスカレーションヒロインズ',
    '侍魂 , スカトロ': '侍魂',
}


def _is_valid_parody(s: str) -> bool:
    """驗證提取的原作名是否合理（排除亂碼、翻譯組名、出版標籤等）。"""
    if not s or len(s) < 2:
        return False
    # 翻譯組名（含漢化/汉化）
    if re.search(r'漢化|汉化', s):
        return False
    # 出版標籤
    if re.match(r'^(あとみっく文庫|二次元ドリーム文庫|フランス書院)\d*$', s):
        return False
    # 多人作者列表（4+ 個空格分隔的詞）
    if len(s.split()) >= 4 and not re.search(r'[のがをはにでと]', s):
        return False
    # 亂碼偵測：含太多罕用字元
    unusual = 0
    total = 0
    for ch in s:
        if '\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff':
            total += 1
        elif '\u3400' <= ch <= '\u4dbf' or '\uf900' <= ch <= '\ufaff':
            unusual += 1
            total += 1
        elif ord(ch) > 127 and ch not in '☆★♪♡×・＜＞！？　＠／':
            # 非常見全形符號
            code = ord(ch)
            if not (0xFF01 <= code <= 0xFF5E):  # 全形 ASCII
                unusual += 1
                total += 1
    if total > 0 and unusual / max(total, 1) > 0.3:
        return False
    return True


def _find_trailing_parens(s: str):
    """找出字串尾部的平衡圓括號內容。支援巢狀括號如 (A (B))。返回 (start_index, content) 或 None。"""
    s = s.rstrip()
    if not s.endswith(')'):
        return None
    depth = 0
    end = len(s)
    for i in range(end - 1, -1, -1):
        if s[i] == ')':
            depth += 1
        elif s[i] == '(':
            depth -= 1
            if depth == 0:
                content = s[i + 1:end - 1].strip()
                return (i, content)
    return None


# 已知非原作尾部圓括號內容
NON_PARODY_TAIL = re.compile(
    r'\s*\(('
    r'JPG|BMP|PNG|CG|MP3|WAV|FLAC|Hi-Res'
    r'|エロ|ロリータ|ふたなり|スカトロ|非エロ|残'
    r'|Chinese|English|Korean|JAP|中文|韓国語|中国語|别扫'
    r'|Digital|修正版|別スキャン|DL版|画像化済|Full HQ Scan'
    r'|イラスト集|CG集|画集|合同誌|再録集|総集編'
    r'|発行\s*\d{4}[-/]\d{2}[-/]\d{2}'
    r')\)\s*$',
    re.IGNORECASE
)

# 尾部場次圓括號（誤判為原作的場次名）
EVENT_TAIL = re.compile(
    r'\s*\('
    r'(C\d+|COMIC1[☆★]\d+|COMIC\d+|SC\d+|COMITIA\d+|AC\d+)'
    r'\)\s*$'
)


def parse_filename(filename: str) -> ParsedDoujinshi:
    """
    解析同人誌檔名，支援多種格式。

    主要格式：
    - (C106) [社團 (作者)] 標題 (原作) [DL版].zip
    - (COMIC1☆8) [社團 (作者)] 標題 (原作).zip
    - (同人誌) [社團 (作者)] 標題 (原作).zip
    - [社團 (作者)] 標題 (原作).zip
    """
    # 去掉 .zip 副檔名
    name = filename
    if name.lower().endswith('.zip'):
        name = name[:-4]

    # URL decode
    name = unquote(name)

    # 底線 -> 空格
    name = name.replace('_', ' ')

    # 偵測 DL版
    is_dl = bool(re.search(r'\[DL版\]|\[Digital\]', name, re.IGNORECASE))

    # 移除前綴垃圾 [xxx@xxx]
    name = PREFIX_JUNK.sub('', name)

    # 移除 (同人誌)/(同人志)/(同人CG集)/(同人CG) 標記，但記錄下來
    name = re.sub(r'\(同人[誌志]\)\s*', '', name)
    name = re.sub(r'\(同人CG(?:集)?\)\s*', '', name)

    # 移除尾部方括號標記 [DL版] [Chinese] 等
    name = SKIP_TAGS.sub('', name)

    # 移除日期標記 [2009-10-28] [2014-04-30] 等
    name = re.sub(r'\s*\[\d{4}[-/]\d{2}[-/]\d{2}\]\s*', ' ', name)

    # 移除 (別スキャン) (修正版) (Full HQ Scan) 等尾部括號標記
    name = re.sub(r'\s*\(別スキャン\)\s*', '', name)
    name = re.sub(r'\s*\(修正版\)\s*', '', name)
    name = re.sub(r'\s*\(Full HQ Scan\)\s*', '', name)

    # 移除 [DLsite限定特典付き] 等商業誌尾部標記
    name = re.sub(r'\s*\[DLsite[^\]]*\]\s*', '', name)

    name = name.strip()

    event = None
    circle = None
    author = None
    title = None
    parody = None
    detected_category = None
    is_commercial = False

    # 0) 先檢查商業誌分類前綴
    commercial_match = COMMERCIAL_PATTERN.match(name)
    if commercial_match:
        cat_raw = commercial_match.group(1).strip()
        detected_category = COMMERCIAL_CATEGORIES.get(cat_raw, cat_raw)
        is_commercial = True
        name = name[commercial_match.end():]

    # 1) 解析場次（商業誌不解析場次）
    if not is_commercial:
        event_match = EVENT_PATTERN.match(name)
        if event_match:
            event_raw = event_match.group(1).strip()
            event = event_raw
            name = name[event_match.end():]

        # 也處理 (同人誌) (C90) 的情況（同人誌已被移除，剩 (C90)）
        if not event:
            retry_match = EVENT_PATTERN.match(name)
            if retry_match:
                event = retry_match.group(1).strip()
                name = name[retry_match.end():]

    # 2) 解析社團和作者：[社團名 (作者名)] 或 [社團名]
    # 跳過日期前綴：[180529] 或 [2012-04-01] 格式
    date_prefix = re.match(r'\[\d{4}[-/]\d{2}[-/]\d{2}\]\s*|\[\d{6}\]\s*', name)
    if date_prefix:
        name = name[date_prefix.end():]

    # 跳過 [RJxxxxxx] DLsite 編號
    rj_prefix = re.match(r'\[RJ\d+\]\s*', name, re.IGNORECASE)
    if rj_prefix:
        name = name[rj_prefix.end():]

    circle_match = re.match(r'\[([^\]]+)\]\s*', name)
    if circle_match:
        circle_raw = circle_match.group(1).strip()
        if is_commercial:
            # 商業誌：[name] 是作者（可能有多個用逗號分隔）
            author = circle_raw
        else:
            # 同人誌：[社團 (作者)] 或 [社團]
            author_match = re.match(r'^(.+?)\s*\(([^)]+)\)$', circle_raw)
            if author_match:
                circle = author_match.group(1).strip()
                author = author_match.group(2).strip()
            else:
                circle = circle_raw
        name = name[circle_match.end():]

    # 3) 剩餘部分：標題 (原作)
    name = name.strip()

    # 全形括號轉半形（部分檔名使用 （） 而非 ()）
    name = name.replace('（', '(').replace('）', ')')

    # 移除尾部所有方括號標記（翻譯組、版本標記等）
    while True:
        m = re.search(r'\s*\[[^\]]*\]\s*$', name)
        if m:
            name = name[:m.start()]
        else:
            break

    # 移除尾部裸版本標記（無括號的 デジタル版 / DL版）
    name = re.sub(r'\s+(?:デジタル版|DL版)\s*$', '', name)

    # 移除已知非原作尾部圓括號
    while True:
        m = NON_PARODY_TAIL.search(name)
        if m:
            name = name[:m.start()]
        else:
            break

    # 移除尾部場次圓括號 (C78) (COMIC1☆5) 等
    while True:
        m = EVENT_TAIL.search(name)
        if m:
            name = name[:m.start()]
        else:
            break

    name = name.strip()

    # 用平衡括號匹配提取原作（支援巢狀括號）
    # 若候選值無效（翻譯組名等），跳過並嘗試下一個
    remaining = name
    while True:
        paren_result = _find_trailing_parens(remaining)
        if not paren_result:
            title = name.strip()
            break
        start, parody_text = paren_result
        # 移除巢狀的 (シリーズ) 後綴
        candidate = re.sub(r'\s*\(シリーズ\)\s*$', '', parody_text).strip()
        if _is_valid_parody(candidate):
            parody = candidate
            title = name[:name.rfind('(' + parody_text[0] if parody_text else '(')].strip()
            # 精確計算 title：用原始 name 截斷到匹配位置
            # 找到 remaining 中 start 對應到 name 中的位置
            tail_len = len(remaining) - start
            title = name[:len(name) - tail_len].strip()
            break
        else:
            # 無效候選，截斷後繼續嘗試
            remaining = remaining[:start].strip()
            # 再次清理尾部非原作括號和場次
            while True:
                m = NON_PARODY_TAIL.search(remaining)
                if m:
                    remaining = remaining[:m.start()]
                else:
                    break
            while True:
                m = EVENT_TAIL.search(remaining)
                if m:
                    remaining = remaining[:m.start()]
                else:
                    break
            remaining = remaining.strip()

    # 清理多餘空格
    if title:
        title = re.sub(r'\s+', ' ', title).strip()
    if not title:
        title = filename  # fallback: 用原始檔名

    # 驗證原作名合理性
    if parody and not _is_valid_parody(parody):
        # 無效的原作名歸入標題
        if title and parody:
            title = f"{title} ({parody})"
        parody = None

    # 正規化原作名
    if parody and parody in PARODY_ALIASES:
        parody = PARODY_ALIASES[parody]

    return ParsedDoujinshi(
        event=event or None,
        circle=circle or None,
        author=author or None,
        title=title or None,
        parody=parody or None,
        is_dl=is_dl,
        detected_category=detected_category,
    )


if __name__ == '__main__':
    # 測試用
    test_names = [
        "(C106) [20NT (ふけまち)] プラナちゃん催眠のお時間です (ブルーアーカイブ) [DL版].zip",
        "(C78) (同人誌) [こりすや] XS #02 永遠の妹 (オリジナル).zip",
        "(COMIC1☆8) [ふらいぱん大魔王 (提灯暗光)] 星宮ケイトは征服されたがってない! (世界征服～謀略のズヴィズダー～).zip",
        "[Hなほん。やさん。(あっきー)] 妊娠ライブ! (ラブライブ!) [DL版].zip",
        "(同人誌) (C90) [嘘つき屋 (よろず)] あしコレJK.zip",
        "[firelee@2DJGAME](C78) (同人誌) [Fatalpulse] 画礫7.zip",
        "(同人CG集) [IVORY] 妹は、エロすぎ！！プレイガールず！.zip",
        "(C86) [PNOグル-プ (山本龍助, 斐川悠希, はせ☆裕)] Carni☆Phanちっく ふぁくとりぃ 6 (Fate／zero, TYPE-MOON).zip",
        "(C88)[珍譜堂 (まるい)] リリのふしぎなリュック (ダンジョンに出会いを求めるのは間違っているだろうか).zip",
        "(同人誌) [180529] [俺だけが得する音声工房 (高月柊也)] ダブルサキュバスの搾精風俗へようこそ! [DL版].zip",
    ]
    for fn in test_names:
        result = parse_filename(fn)
        print(f"\n{fn}")
        print(f"  場次={result.event} 社團={result.circle} 作者={result.author}")
        print(f"  標題={result.title} 原作={result.parody} DL={result.is_dl}")
