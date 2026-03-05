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

    # 移除 (同人誌)/(同人志)/(同人CG集) 標記，但記錄下來
    name = re.sub(r'\(同人[誌志]\)\s*', '', name)
    name = re.sub(r'\(同人CG[集]\)\s*', '', name)

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
    # 從最後找 (原作)
    name = name.strip()
    parody_match = re.search(r'\(([^)]+)\)\s*$', name)
    if parody_match:
        parody = parody_match.group(1).strip()
        title = name[:parody_match.start()].strip()
    else:
        title = name.strip()

    # 清理多餘空格
    if title:
        title = re.sub(r'\s+', ' ', title).strip()
    if not title:
        title = filename  # fallback: 用原始檔名

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
