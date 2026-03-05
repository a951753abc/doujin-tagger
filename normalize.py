"""日文文字正規化與重複偵測模組"""

import re
import unicodedata
from collections import defaultdict

import pykakasi

_kks = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    """將日文文字轉為 romaji（平文式）。"""
    result = _kks.convert(text)
    return "".join(item["hepburn"] for item in result)


def kata_to_hira(text: str) -> str:
    """片假名 → 平假名。"""
    out = []
    for ch in text:
        cp = ord(ch)
        # カタカナ (30A1-30F6) → ひらがな (3041-3096)
        if 0x30A1 <= cp <= 0x30F6:
            out.append(chr(cp - 0x60))
        # 片假名長音 ー 保留
        else:
            out.append(ch)
    return "".join(out)


def normalize_for_compare(text: str) -> str:
    """
    產生正規化比較鍵。
    - NFKC 正規化（全形→半形等）
    - 片假名→平假名
    - 小寫
    - 移除空白、標點
    """
    if not text:
        return ""
    # NFKC: 全形英數→半形、合字分解等
    s = unicodedata.normalize("NFKC", text)
    # 片假名→平假名
    s = kata_to_hira(s)
    # 小寫
    s = s.lower()
    # 移除空白和常見標點
    s = re.sub(r'[\s\-_/!?.,:;・♥☆★♪~～「」『』【】（）()＝=＆&＋+\'"]+', "", s)
    return s


def make_romaji_key(text: str) -> str:
    """產生 romaji 比較鍵（用於跨文字系統比對）。"""
    if not text:
        return ""
    romaji = to_romaji(text)
    return normalize_for_compare(romaji)


def has_japanese(text: str) -> bool:
    """檢查是否包含日文字元（漢字、平假名、片假名）。"""
    for ch in text:
        cp = ord(ch)
        if (0x3040 <= cp <= 0x309F or   # 平假名
            0x30A0 <= cp <= 0x30FF or    # 片假名
            0x4E00 <= cp <= 0x9FFF or    # CJK 統一漢字
            0x3400 <= cp <= 0x4DBF):     # CJK 統一漢字擴展 A
            return True
    return False


def japanese_char_ratio(text: str) -> float:
    """日文字元佔比（用於排序偏好日文名）。"""
    if not text:
        return 0.0
    jp_count = sum(1 for ch in text if has_japanese(ch))
    return jp_count / len(text)


def find_duplicates(values_with_counts: list[tuple[str, int]]) -> list[dict]:
    """
    從 (value, count) 列表中找出可能的重複組。

    回傳格式：
    [
        {
            "canonical": "推薦的正規名（日文優先）",
            "variants": [
                {"value": "原始值", "count": 使用次數, "is_japanese": bool},
                ...
            ],
            "total_count": 總使用次數
        },
        ...
    ]
    """
    # 策略 1: 正規化比較鍵分組（片假名/平假名/空白/標點統一）
    norm_groups = defaultdict(list)
    for value, count in values_with_counts:
        key = normalize_for_compare(value)
        if key:
            norm_groups[key].append((value, count))

    # 策略 2: romaji 比較鍵分組（跨文字系統）
    romaji_groups = defaultdict(list)
    for value, count in values_with_counts:
        key = make_romaji_key(value)
        if key:
            romaji_groups[key].append((value, count))

    # 合併兩種策略的結果，用 union-find
    parent = {}
    for value, _ in values_with_counts:
        parent[value] = value

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # 從 norm_groups 合併
    for members in norm_groups.values():
        if len(members) > 1:
            for i in range(1, len(members)):
                union(members[0][0], members[i][0])

    # 從 romaji_groups 合併
    for members in romaji_groups.values():
        if len(members) > 1:
            for i in range(1, len(members)):
                union(members[0][0], members[i][0])

    # 收集最終分組
    final_groups = defaultdict(list)
    value_counts = {v: c for v, c in values_with_counts}
    for value in parent:
        root = find(value)
        final_groups[root].append(value)

    # 只保留有多個變體的組
    results = []
    for members in final_groups.values():
        if len(members) < 2:
            continue

        variants = []
        for v in members:
            variants.append({
                "value": v,
                "count": value_counts[v],
                "is_japanese": has_japanese(v),
            })

        # 排序：日文優先，然後按使用次數降序
        variants.sort(key=lambda x: (-x["is_japanese"], -x["count"]))

        # 推薦正規名：優先選日文、次選使用最多的
        canonical = variants[0]["value"]

        results.append({
            "canonical": canonical,
            "variants": variants,
            "total_count": sum(v["count"] for v in variants),
        })

    # 按總數降序排
    results.sort(key=lambda x: -x["total_count"])
    return results


def find_duplicates_for_field(conn, field: str) -> list[dict]:
    """從資料庫中讀取指定欄位的值，偵測重複。"""
    if field not in ("event", "circle", "author", "parody"):
        return []
    rows = conn.execute(
        f"SELECT {field}, COUNT(*) as cnt FROM doujinshi "
        f"WHERE {field} IS NOT NULL AND {field} != '' "
        f"GROUP BY {field}"
    ).fetchall()
    values_with_counts = [(r[0], r[1]) for r in rows]
    return find_duplicates(values_with_counts)


def merge_field_values(conn, field: str, canonical: str, old_values: list[str]):
    """將 old_values 全部合併為 canonical。"""
    if field not in ("event", "circle", "author", "parody"):
        return 0
    if not old_values:
        return 0
    placeholders = ",".join("?" * len(old_values))
    cur = conn.execute(
        f"UPDATE doujinshi SET {field} = ?, updated_at = CURRENT_TIMESTAMP "
        f"WHERE {field} IN ({placeholders})",
        [canonical] + old_values,
    )
    conn.commit()
    return cur.rowcount
