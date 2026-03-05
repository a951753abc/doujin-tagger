"""Web 搜尋多來源補標模組

三層策略：
  Layer 1: DLsite 查詢（CG集/DL版最有效）
  Layer 2: 通用 Web 搜尋（Google）
  Layer 3: 模式推斷（不需網路）
"""

import argparse
import json
import re
import sqlite3
import sys
import time
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

import config
from models import get_db, get_doujinshi, update_doujinshi

# ── 常數 ──

DLSITE_SEARCH_URL = "https://www.dlsite.com/maniax/fsr/=/language/jp/keyword/{query}/per_page/30/page/1"
DLSITE_PRODUCT_URL = "https://www.dlsite.com/maniax/work/=/product_id/{rj_code}.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}

# DLsite 常見的原作對照（genre → parody 名）
DLSITE_GENRE_TO_PARODY = {
    "オリジナル": "オリジナル",
    "創作": "オリジナル",
}

# DLsite 的屬性/類型標籤（不是原作名，不應被當成 parody）
DLSITE_GENRE_TAGS = {
    # 屬性
    "人妻", "おっぱい", "ハーレム", "寝取り", "寝取られ", "連続絶頂", "断面図",
    "ギャル", "メイド", "シスター", "百合", "おねショタ", "ショタ", "少女",
    "ロリ", "巨乳", "貧乳", "熟女", "痴女", "女王様", "お嬢様", "幼なじみ",
    "妹", "姉", "母", "義母", "義妹", "義姉", "女教師", "看護師", "OL",
    "女騎士", "魔法少女", "くノ一", "エルフ", "獣耳", "触手", "ふたなり",
    "男の娘", "女装", "TSF", "異種姦", "催眠", "洗脳", "調教", "奴隷",
    "緊縛", "拘束", "監禁", "陵辱", "輪姦", "痴漢", "露出", "野外",
    "アナル", "フェラチオ", "パイズリ", "手コキ", "足コキ", "中出し",
    "顔射", "ぶっかけ", "飲尿", "スカトロ", "母乳", "搾乳", "妊娠",
    "孕ませ", "出産", "体操服", "スクール水着", "制服", "水着", "裸エプロン",
    "コスプレ", "眼鏡", "ツインテール", "ポニーテール", "黒髪", "金髪",
    # プレイ・ジャンル
    "総集編", "シリーズもの", "癒し", "ほのぼの", "コメディ", "ダーク",
    "ファンタジー", "SF", "学園もの", "日常", "恋愛", "ラブコメ",
    "バトル", "アクション", "ミステリー", "ホラー", "グロ",
    "汁/液大量", "おさわり", "中出", "3P", "4P", "乱交",
    # DLsite 追加標籤
    "ASMR", "3D作品", "萌え", "日常/生活", "ほのぼの/癒し",
    "音声作品", "動画作品", "CG・イラスト", "マンガ作品",
    "RPG", "シミュレーション", "アドベンチャー", "デジタルノベル",
    "ボイスドラマ", "バイノーラル", "ダンジョンRPG",
    "伯爵", "異世界", "冒険", "魔法", "王族", "貴族",
    "女戦士", "女勇者", "女幹部", "姫", "巫女", "悪魔",
    "天使", "吸血鬼", "サキュバス", "ドラゴン", "スライム",
    "ゾンビ", "モンスター", "ゴブリン", "オーク", "人外",
    "褐色", "白髪", "銀髪", "赤髪", "碧眼", "ケモミミ",
    "ネコミミ", "イヌ耳", "ウサギ耳", "ドワーフ", "ダークエルフ",
    "ぺったんこ", "ムチムチ", "爆乳", "超乳",
    "和姦", "純愛", "イチャラブ", "甘々", "逆レイプ", "強制",
    "屈辱", "羞恥", "言葉責め", "目隠し", "睡眠姦", "泥酔",
    "薬物", "媚薬", "改造", "寄生", "浸食", "腐敗",
    "蟲姦", "植物姦", "機械姦", "拡張", "二穴", "三穴",
    "手マン", "クンニ", "シックスナイン", "素股", "尻コキ",
    "おもちゃ", "バイブ", "ローター", "拘束具",
    "魔法使い", "戦士", "僧侶", "盗賊", "召喚師",
    "処女", "童貞", "年上", "年下", "同級生", "先輩", "後輩",
    "主従", "上司", "部下", "ご主人様", "奴隷",
}

# RJ 編號 pattern
RJ_PATTERN = re.compile(r'(RJ\d{6,8})', re.IGNORECASE)

# CG 集判定用關鍵字
CG_KEYWORDS = re.compile(r'CG集|CG set|イラスト集|画集', re.IGNORECASE)

def _delay():
    """請求間隔，避免被封鎖。"""
    time.sleep(config.REQUEST_DELAY)


# ── Layer 1: DLsite 搜尋 ──

def extract_rj_code(text: str) -> Optional[str]:
    """從文字中提取 RJ 編號。"""
    m = RJ_PATTERN.search(text)
    return m.group(1).upper() if m else None


def search_dlsite_by_rj(rj_code: str) -> Optional[dict]:
    """用 RJ 編號直接查詢 DLsite 產品頁。"""
    url = DLSITE_PRODUCT_URL.format(rj_code=rj_code)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        return _parse_dlsite_product_page(resp.text, url)
    except requests.RequestException:
        return None


def search_dlsite(query: str) -> list[dict]:
    """在 DLsite 搜尋，回傳匹配結果列表。"""
    url = DLSITE_SEARCH_URL.format(query=quote_plus(query))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
    except requests.RequestException:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # 搜尋結果列表中的每個作品
    for item in soup.select(".search_result_img_box_inner, .multiline_truncate"):
        link = item.select_one("a[href*='/product_id/']")
        if not link:
            continue
        href = link.get("href", "")
        title_text = link.get_text(strip=True)
        rj = extract_rj_code(href)
        if rj:
            results.append({
                "title": title_text,
                "url": href,
                "rj_code": rj,
                "source": "dlsite_search",
            })

    return results[:5]  # 最多回傳 5 筆


def fetch_dlsite_product(url: str) -> Optional[dict]:
    """取得 DLsite 產品頁詳細資訊。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        return _parse_dlsite_product_page(resp.text, url)
    except requests.RequestException:
        return None


def _parse_dlsite_product_page(html: str, url: str) -> Optional[dict]:
    """解析 DLsite 產品頁面，提取 metadata。"""
    soup = BeautifulSoup(html, "html.parser")

    result = {"url": url, "source": "dlsite", "confidence": 0.85}

    # 標題
    title_el = soup.select_one("#work_name a, #work_name")
    if title_el:
        result["title"] = title_el.get_text(strip=True)

    # 社團名
    circle_el = soup.select_one("span.maker_name a")
    if circle_el:
        result["circle"] = circle_el.get_text(strip=True)

    # 作者（有時在社團名下方）
    author_el = soup.select_one('tr:has(th:-soup-contains("作者")) td a')
    if not author_el:
        # 備用選擇器
        for th in soup.select("th"):
            if "作者" in th.get_text():
                td = th.find_next_sibling("td")
                if td:
                    a = td.select_one("a")
                    if a:
                        result["author"] = a.get_text(strip=True)
                    else:
                        result["author"] = td.get_text(strip=True)
                break
    else:
        result["author"] = author_el.get_text(strip=True)

    # 作品分類/原作（ジャンル）
    genre_els = soup.select('div.main_genre a, tr:has(th:-soup-contains("ジャンル")) td a')
    if not genre_els:
        for th in soup.select("th"):
            if "ジャンル" in th.get_text():
                td = th.find_next_sibling("td")
                if td:
                    genre_els = td.select("a")
                break

    genres = [el.get_text(strip=True) for el in genre_els]

    # 嘗試從分類推斷原作
    if genres:
        # 先看有沒有直接是原作名的（排除 DLsite 屬性標籤）
        parody_candidates = [
            g for g in genres
            if g not in DLSITE_GENRE_TO_PARODY
            and g not in DLSITE_GENRE_TAGS
            and len(g) > 1
        ]
        if parody_candidates:
            result["parody"] = parody_candidates[0]
        else:
            # 所有 genre 都是屬性標籤或明確標記為原創 → オリジナル
            result["parody"] = "オリジナル"

    # 如果有標題但沒什麼有用的其他欄位，降低信心度
    if "circle" not in result and "parody" not in result:
        result["confidence"] = 0.3

    return result if ("title" in result or "circle" in result) else None


def search_dlsite_combined(item: dict) -> list[dict]:
    """組合 DLsite 搜尋策略。"""
    results = []

    # 優先用 RJ 碼
    rj_code = extract_rj_code(item.get("filename", ""))
    if rj_code:
        detail = search_dlsite_by_rj(rj_code)
        if detail:
            detail["confidence"] = 0.95
            results.append(detail)
            return results

    # 用社團 + 標題搜尋
    query_parts = []
    if item.get("circle"):
        query_parts.append(item["circle"])
    if item.get("title"):
        query_parts.append(item["title"])

    if query_parts:
        query = " ".join(query_parts)
        search_results = search_dlsite(query)
        _delay()

        # 取第一個結果的詳細頁
        for sr in search_results[:2]:
            detail = fetch_dlsite_product(sr["url"])
            if detail:
                results.append(detail)
                _delay()

    return results


# ── Layer 2: 通用 Web 搜尋 ──

def search_web(query: str) -> list[dict]:
    """用搜尋引擎搜尋，回傳摘要結果。

    使用 Google 搜尋，解析結果頁面。
    """
    search_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=ja&num=5"
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
    except requests.RequestException:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # Google 搜尋結果
    for g in soup.select("div.g, div[data-sokoban-container]"):
        link = g.select_one("a[href^='http']")
        title_el = g.select_one("h3")
        snippet_el = g.select_one("div.VwiC3b, span.aCOpRe, div[data-sncf]")

        if link and title_el:
            results.append({
                "title": title_el.get_text(strip=True),
                "url": link.get("href", ""),
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                "source": "web",
            })

    return results[:5]


def extract_parody_from_web_results(results: list[dict], item: dict) -> Optional[dict]:
    """從 Web 搜尋結果中推斷原作。"""
    for r in results:
        text = f"{r.get('title', '')} {r.get('snippet', '')}"

        # 常見的原作標記模式
        # 「作品名（原作名）」或「原作: xxx」
        parody_match = re.search(r'[（(]([^）)]+)[）)]', text)
        if parody_match:
            candidate = parody_match.group(1)
            # 過濾掉太短或是常見垃圾詞
            if len(candidate) >= 2 and candidate not in {"同人誌", "CG集", "DL版", "中文", "日本語"}:
                return {
                    "parody": candidate,
                    "source": "web",
                    "url": r["url"],
                    "confidence": 0.5,
                }

    return None


# ── Layer 3: 模式推斷 ──

def infer_from_patterns(conn: sqlite3.Connection, item: dict) -> Optional[dict]:
    """不需網路的本地推斷。"""
    filename = item.get("filename", "")
    title = item.get("title", "")

    # CG 集 + 無已知系列作品 → 很可能是オリジナル
    is_cg = bool(CG_KEYWORDS.search(filename)) or bool(CG_KEYWORDS.search(title))
    is_dl = item.get("is_dl", 0)

    if is_cg:
        return {
            "parody": "オリジナル",
            "source": "pattern_infer",
            "confidence": 0.6,
            "reason": "CG集通常為原創作品",
        }

    # 同社團的已知原作推斷
    circle = item.get("circle")
    if circle:
        row = conn.execute(
            """SELECT parody, COUNT(*) as cnt
               FROM doujinshi
               WHERE circle = ? AND parody IS NOT NULL AND parody != ''
               GROUP BY parody
               ORDER BY cnt DESC
               LIMIT 1""",
            (circle,)
        ).fetchone()
        if row and row["cnt"] >= 2:
            return {
                "parody": row["parody"],
                "source": "circle_infer",
                "confidence": 0.4,
                "reason": f"同社團「{circle}」有 {row['cnt']} 筆作品為「{row['parody']}」",
            }

    return None


# ── 組合策略 ──

def enrich_item(conn: sqlite3.Connection, item_id: int) -> dict:
    """組合三層策略，回傳建議 metadata。

    回傳格式：
    {
        "item_id": int,
        "current": {原始資料},
        "suggestions": [
            {"parody": "xxx", "circle": "xxx", "confidence": 0.8, "source": "dlsite", ...},
            ...
        ]
    }
    """
    item = get_doujinshi(conn, item_id)
    if not item:
        return {"error": "not found", "item_id": item_id, "suggestions": []}

    suggestions = []

    # Layer 3: 模式推斷（最快，先做）
    pattern_result = infer_from_patterns(conn, item)
    if pattern_result:
        suggestions.append(pattern_result)

    # Layer 1: DLsite
    try:
        dlsite_results = search_dlsite_combined(item)
        suggestions.extend(dlsite_results)
    except Exception as e:
        print(f"  DLsite 搜尋失敗: {e}", file=sys.stderr)

    # Layer 2: 通用 Web 搜尋
    try:
        query_parts = ["同人誌"]
        if item.get("circle"):
            query_parts.append(item["circle"])
        if item.get("title"):
            query_parts.append(item["title"])
        query = " ".join(query_parts)
        web_results = search_web(query)
        _delay()

        web_suggestion = extract_parody_from_web_results(web_results, item)
        if web_suggestion:
            suggestions.append(web_suggestion)
    except Exception as e:
        print(f"  Web 搜尋失敗: {e}", file=sys.stderr)

    # 按 confidence 排序
    suggestions.sort(key=lambda s: s.get("confidence", 0), reverse=True)

    return {
        "item_id": item_id,
        "current": {
            "title": item.get("title"),
            "circle": item.get("circle"),
            "author": item.get("author"),
            "parody": item.get("parody"),
            "event": item.get("event"),
            "filename": item.get("filename"),
        },
        "suggestions": suggestions,
    }


def apply_suggestion(conn: sqlite3.Connection, item_id: int, suggestion: dict) -> dict:
    """將建議寫入資料庫。只更新非空的建議欄位，且只更新目前為空的欄位。"""
    item = get_doujinshi(conn, item_id)
    if not item:
        return {"error": "not found"}

    fields_to_update = {}
    for field in ("circle", "author", "parody", "event"):
        suggested_value = suggestion.get(field)
        current_value = item.get(field)
        if suggested_value and not current_value:
            fields_to_update[field] = suggested_value

    if fields_to_update:
        update_doujinshi(conn, item_id, fields_to_update)
        return {"updated": fields_to_update, "item_id": item_id}
    return {"updated": {}, "item_id": item_id, "message": "沒有需要更新的欄位"}


# ── 批次處理 ──

def get_uncategorized(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    """取得完全未分類的項目。"""
    rows = conn.execute(
        """SELECT id, filename, filepath, event, circle, author, title, parody, is_dl
           FROM doujinshi
           WHERE (event IS NULL OR event = '')
             AND (circle IS NULL OR circle = '')
             AND (author IS NULL OR author = '')
             AND (parody IS NULL OR parody = '')
           LIMIT ?""",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_missing_field(conn: sqlite3.Connection, field: str, limit: int = 100) -> list[dict]:
    """取得缺少特定欄位的項目。"""
    if field not in ("event", "circle", "author", "parody"):
        raise ValueError(f"不支援的欄位: {field}")
    rows = conn.execute(
        f"""SELECT id, filename, filepath, event, circle, author, title, parody, is_dl
            FROM doujinshi
            WHERE ({field} IS NULL OR {field} = '')
            LIMIT ?""",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def batch_enrich(conn: sqlite3.Connection, items: list[dict],
                 auto_apply: bool = False, min_confidence: float = 0.8) -> list[dict]:
    """批次處理，回傳結果列表。"""
    results = []
    total = len(items)

    for i, item in enumerate(items, 1):
        item_id = item["id"]
        print(f"[{i}/{total}] 處理: {item.get('filename', item_id)}")

        enrichment = enrich_item(conn, item_id)
        suggestions = enrichment.get("suggestions", [])

        if suggestions:
            best = suggestions[0]
            conf = best.get("confidence", 0)
            print(f"  最佳建議: {best.get('source')} (信心度 {conf:.0%})")
            for k in ("circle", "author", "parody", "event"):
                if k in best:
                    print(f"    {k}: {best[k]}")

            if auto_apply and conf >= min_confidence:
                result = apply_suggestion(conn, item_id, best)
                if result.get("updated"):
                    print(f"  ✓ 已自動套用: {result['updated']}")
                enrichment["auto_applied"] = result.get("updated", {})
        else:
            print("  無建議")

        results.append(enrichment)
        print()

    return results


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="Web 搜尋補標工具")
    parser.add_argument("--dry-run", action="store_true", help="預覽模式（不寫入）")
    parser.add_argument("--auto", action="store_true", help="自動補標（僅高信心度）")
    parser.add_argument("--confidence", type=float, default=0.8, help="自動補標的最低信心度（預設 0.8）")
    parser.add_argument("--limit", type=int, default=50, help="處理筆數上限（預設 50）")
    parser.add_argument("--uncategorized-only", action="store_true", help="只處理完全未分類")
    parser.add_argument("--missing", type=str, help="只處理缺少特定欄位（event/circle/author/parody）")
    args = parser.parse_args()

    conn = get_db()

    # 選取要處理的項目
    if args.uncategorized_only:
        items = get_uncategorized(conn, args.limit)
        print(f"找到 {len(items)} 筆完全未分類項目")
    elif args.missing:
        items = get_missing_field(conn, args.missing, args.limit)
        print(f"找到 {len(items)} 筆缺少 {args.missing} 的項目")
    else:
        # 預設：處理缺原作的
        items = get_missing_field(conn, "parody", args.limit)
        print(f"找到 {len(items)} 筆缺原作的項目")

    if not items:
        print("沒有需要處理的項目")
        conn.close()
        return

    auto_apply = args.auto and not args.dry_run
    results = batch_enrich(conn, items, auto_apply=auto_apply, min_confidence=args.confidence)

    # 統計
    total = len(results)
    has_suggestion = sum(1 for r in results if r.get("suggestions"))
    auto_applied = sum(1 for r in results if r.get("auto_applied"))

    print("=" * 50)
    print(f"處理完成")
    print(f"  總計: {total} 筆")
    print(f"  有建議: {has_suggestion} 筆")
    if auto_apply:
        print(f"  已自動套用: {auto_applied} 筆")
    if args.dry_run:
        print("  (預覽模式，未寫入任何資料)")

    conn.close()


if __name__ == "__main__":
    main()
