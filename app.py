"""同人誌 TAG 搜尋系統 - Flask 應用"""

import io
import json
import os
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, make_response, g

from PIL import Image as _PILImage

import config
from models import (
    get_db, init_db, search_doujinshi, get_doujinshi,
    update_doujinshi, add_tag, remove_tag, get_all_tags, get_filter_options,
    batch_add_tag, batch_update, get_stats, get_setting, set_setting, get_all_settings,
    move_doujinshi
)
from normalize import find_duplicates_for_field, merge_field_values
from thumbs import ThumbWorker, get_thumbnail_path

app = Flask(__name__)
thumb_worker = ThumbWorker(max_workers=config.THUMB_WORKERS)

# 1x1 透明 webp placeholder（啟動時生成一次）
_ph = io.BytesIO()
_PILImage.new('RGBA', (1, 1), (0, 0, 0, 0)).save(_ph, 'WEBP')
PLACEHOLDER_WEBP = _ph.getvalue()


def _is_path_under(filepath: str, allowed_roots: list[str]) -> bool:
    """安全的路徑包含檢查（避免 startswith 前綴誤判）。"""
    norm = Path(filepath).resolve()
    return any(norm.is_relative_to(Path(r).resolve()) for r in allowed_roots)


def _get_allowed_roots(db=None):
    """從 DB settings 動態取得允許的根目錄。"""
    from scan import get_scan_roots
    conn = db or get_db()
    roots = get_scan_roots(conn)
    return [str(r["path"]) for r in roots]


def _get_validated_item(did):
    """取得 doujinshi 並驗證路徑合法性。回傳 (item, filepath) 或 (None, error_response)。"""
    item = get_doujinshi(g.db, did)
    if not item:
        return None, (jsonify({"error": "not found"}), 404)

    filepath = item['filepath']
    allowed = _get_allowed_roots(g.db)
    if not _is_path_under(filepath, allowed):
        return None, (jsonify({"error": "invalid path"}), 403)

    return item, filepath


@app.before_request
def before_request():
    """每個 request 建立 DB 連線 + CSRF 檢查。"""
    # CSRF: 寫入操作檢查 Origin / Referer
    if request.method in ('POST', 'PUT', 'DELETE'):
        origin = request.headers.get('Origin') or request.headers.get('Referer', '')
        if origin and not any(h in origin for h in ('localhost', '127.0.0.1')):
            return jsonify({"error": "CSRF check failed"}), 403
    g.db = get_db()


@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db:
        db.close()


# ── 頁面路由 ──

@app.route('/')
def index():
    return render_template('index.html')


# ── API 路由 ──

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '')
    event = request.args.get('event', '')
    circle = request.args.get('circle', '')
    author = request.args.get('author', '')
    parody = request.args.get('parody', '')
    tags = request.args.getlist('tags')
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(200, max(1, int(request.args.get('per_page', 50))))
    except (ValueError, TypeError):
        page, per_page = 1, 50
    sort = request.args.get('sort', 'event')
    order = request.args.get('order', 'desc')
    category = request.args.get('category', '')

    source = request.args.get('source', '')

    result = search_doujinshi(g.db, query, event, circle, author, parody,
                               tags or None, page, per_page, sort, order,
                               category, source)
    return jsonify(result)


@app.route('/api/filters')
def api_filters():
    return jsonify(get_filter_options(g.db))


@app.route('/api/doujinshi/<int:did>')
def api_get(did):
    item = get_doujinshi(g.db, did)
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@app.route('/api/doujinshi/<int:did>', methods=['PUT'])
def api_update(did):
    fields = request.get_json() or {}
    update_doujinshi(g.db, did, fields)
    return jsonify(get_doujinshi(g.db, did))


@app.route('/api/doujinshi/<int:did>/tags', methods=['POST'])
def api_add_tag(did):
    data = request.get_json() or {}
    tag_name = data.get('name', '').strip()
    if not tag_name:
        return jsonify({"error": "tag name required"}), 400
    tag = add_tag(g.db, did, tag_name)
    return jsonify(tag)


@app.route('/api/doujinshi/<int:did>/tags/<int:tid>', methods=['DELETE'])
def api_remove_tag(did, tid):
    remove_tag(g.db, did, tid)
    return jsonify({"ok": True})


@app.route('/api/tags')
def api_tags():
    return jsonify(get_all_tags(g.db))


@app.route('/open/<int:did>')
def open_file(did):
    item, filepath = _get_validated_item(did)
    if item is None:
        return filepath  # filepath is error response

    if not os.path.exists(filepath):
        return jsonify({"error": "file not found"}), 404

    config.open_file_cross_platform(filepath)
    return jsonify({"ok": True})


@app.route('/api/doujinshi/<int:did>', methods=['DELETE'])
def api_delete(did):
    """刪除 zip 檔案及 DB 紀錄。僅限 .zip 檔案。"""
    item, filepath = _get_validated_item(did)
    if item is None:
        return filepath  # filepath is error response

    # 僅限 zip 檔
    if not filepath.lower().endswith('.zip'):
        return jsonify({"error": "僅限刪除 ZIP 檔案"}), 403

    # 刪除實體檔案（直接操作，避免 TOCTOU）
    try:
        os.remove(filepath)
    except FileNotFoundError:
        pass

    # 刪除 DB 紀錄（含關聯 tags）
    from models import delete_doujinshi
    delete_doujinshi(g.db, did)

    return jsonify({"ok": True, "filename": item['filename']})


@app.route('/api/doujinshi/<int:did>/web-search', methods=['POST'])
def api_web_search(did):
    """觸發 Web 搜尋建議，回傳建議列表（不自動寫入）。"""
    from web_enrich import enrich_item
    result = enrich_item(g.db, did)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route('/api/doujinshi/<int:did>/apply-suggestion', methods=['POST'])
def api_apply_suggestion(did):
    """使用者確認後寫入選定的建議。"""
    from web_enrich import apply_suggestion
    suggestion = request.get_json() or {}
    result = apply_suggestion(g.db, did, suggestion)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route('/api/duplicates')
def api_duplicates():
    """偵測指定欄位的重複值。"""
    field = request.args.get('field', 'parody')
    dupes = find_duplicates_for_field(g.db, field)
    return jsonify(dupes)


@app.route('/api/merge', methods=['POST'])
def api_merge():
    """合併重複值。"""
    data = request.get_json() or {}
    field = data.get('field', '')
    canonical = data.get('canonical', '')
    old_values = data.get('old_values', [])
    if not field or not canonical or not old_values:
        return jsonify({"error": "missing field, canonical, or old_values"}), 400
    count = merge_field_values(g.db, field, canonical, old_values)
    return jsonify({"ok": True, "updated": count})


@app.route('/api/batch/tags', methods=['POST'])
def api_batch_tags():
    """批次加 tag。"""
    data = request.get_json() or {}
    ids = data.get('ids', [])
    name = data.get('name', '').strip()
    if not ids or not name:
        return jsonify({"error": "ids and name required"}), 400
    result = batch_add_tag(g.db, ids, name)
    return jsonify(result)


@app.route('/api/batch/move', methods=['POST'])
def api_batch_move():
    """批次搬移檔案到歸檔區（依場次分資料夾）。"""
    import shutil
    data = request.get_json() or {}
    ids = data.get('ids', [])
    target_root = data.get('target_root', '').strip()
    if not ids or not target_root:
        return jsonify({"error": "ids and target_root required"}), 400

    # 驗證 target_root 是歸檔區路徑
    from scan import get_scan_roots
    roots = get_scan_roots(g.db)
    archive_paths = [str(r["path"].resolve()) for r in roots if r["source"] == "archive"]
    target_resolved = str(Path(target_root).resolve())
    if target_resolved not in archive_paths:
        return jsonify({"error": "目標路徑不在歸檔區設定中"}), 403

    allowed = _get_allowed_roots(g.db)
    moved = 0
    errors = []
    for did in ids:
        item = get_doujinshi(g.db, did)
        if not item:
            errors.append({"id": did, "error": "not found"})
            continue

        old_path = item['filepath']
        if not _is_path_under(old_path, allowed):
            errors.append({"id": did, "error": "invalid source path"})
            continue

        if not os.path.exists(old_path):
            errors.append({"id": did, "error": "file not found"})
            continue

        # 決定子資料夾：場次名稱或「未分類」
        event_folder = item['event'].strip() if item.get('event') and item['event'].strip() else '未分類'
        dest_dir = Path(target_root) / event_folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        filename = Path(old_path).name
        dest_path = dest_dir / filename

        if dest_path.exists():
            errors.append({"id": did, "error": f"目標已存在: {filename}"})
            continue

        try:
            shutil.move(old_path, str(dest_path))
        except OSError as e:
            errors.append({"id": did, "error": str(e)})
            continue

        move_doujinshi(g.db, did, str(dest_path), event_folder, "archive")
        moved += 1

    return jsonify({"moved": moved, "errors": errors})


@app.route('/api/batch/update', methods=['PUT'])
def api_batch_update():
    """批次更新欄位。"""
    data = request.get_json() or {}
    ids = data.get('ids', [])
    fields = data.get('fields', {})
    if not ids or not fields:
        return jsonify({"error": "ids and fields required"}), 400
    result = batch_update(g.db, ids, fields)
    return jsonify(result)


@app.route('/api/thumb/<int:did>')
def api_thumb(did):
    """回傳縮圖。若尚未生成，提交背景任務並回傳 placeholder。"""
    thumb = get_thumbnail_path(did)
    if thumb:
        return send_file(thumb, mimetype='image/webp',
                         max_age=86400)

    item = get_doujinshi(g.db, did)
    if item:
        thumb_worker.submit(item['filepath'], did)
    # 回傳 1x1 透明 webp placeholder（不快取，讓前端輪詢能取到新縮圖）
    resp = make_response(PLACEHOLDER_WEBP)
    resp.headers['Content-Type'] = 'image/webp'
    resp.headers['Cache-Control'] = 'no-store'
    return resp, 202


@app.route('/api/thumbs/clear', methods=['POST'])
def api_clear_thumbs():
    """清除所有縮圖快取，讓縮圖以新設定重新生成。"""
    import thumbs as thumbs_mod
    count = 0
    for f in thumbs_mod.THUMB_DIR.iterdir():
        if f.suffix in ('.webp', '.failed'):
            f.unlink()
            count += 1
    return jsonify({"ok": True, "cleared": count})


@app.route('/read/<int:did>')
def read_file(did):
    """用設定的閱讀器（Honeyview）開啟檔案。"""
    item, filepath = _get_validated_item(did)
    if item is None:
        return filepath  # filepath is error response

    if not os.path.exists(filepath):
        return jsonify({"error": "file not found"}), 404

    viewer = get_setting(g.db, 'viewer_path', config.default_viewer())
    if not os.path.exists(viewer):
        return jsonify({"error": "閱讀器不存在"}), 404

    subprocess.Popen([viewer, filepath])
    return jsonify({"ok": True})


@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    settings = get_all_settings(g.db)
    if 'viewer_path' not in settings:
        settings['viewer_path'] = config.default_viewer()
    if 'scan_roots' not in settings:
        settings['scan_roots'] = '[]'
    if 'thumb_size' not in settings:
        settings['thumb_size'] = config.get("thumb_size", "300x400")
    if 'thumb_quality' not in settings:
        settings['thumb_quality'] = str(config.THUMB_QUALITY)
    return jsonify(settings)


@app.route('/api/settings', methods=['PUT'])
def api_update_settings():
    data = request.get_json() or {}
    allowed_keys = {'viewer_path', 'scan_roots', 'thumb_size', 'thumb_quality'}
    for key, value in data.items():
        if key in allowed_keys:
            # scan_roots 需要是 JSON 字串
            if key == 'scan_roots' and isinstance(value, list):
                value = json.dumps(value, ensure_ascii=False)
            if key == 'thumb_size':
                value = str(value).strip()
                if not _valid_thumb_size(value):
                    return jsonify({"error": "縮圖尺寸格式錯誤，請用 寬x高 格式（如 300x400）"}), 400
            if key == 'thumb_quality':
                try:
                    q = int(value)
                    if not (1 <= q <= 100):
                        raise ValueError
                    value = str(q)
                except (ValueError, TypeError):
                    return jsonify({"error": "品質須為 1-100 之間的整數"}), 400
            set_setting(g.db, key, value)
    # 即時更新 thumbs 模組的設定
    _apply_thumb_settings(g.db)
    return jsonify({"ok": True})


def _valid_thumb_size(s: str) -> bool:
    """驗證 thumb_size 格式如 '300x400'。"""
    import re
    return bool(re.match(r'^\d{1,4}x\d{1,4}$', s))


def _apply_thumb_settings(db):
    """將 DB 中的縮圖設定套用到 thumbs 模組。"""
    import thumbs as thumbs_mod
    ts = get_setting(db, 'thumb_size', '')
    if ts and _valid_thumb_size(ts):
        thumbs_mod.THUMB_SIZE = tuple(int(x) for x in ts.split('x'))
    tq = get_setting(db, 'thumb_quality', '')
    if tq:
        try:
            thumbs_mod.THUMB_QUALITY = int(tq)
        except ValueError:
            pass


@app.route('/api/stats')
def api_stats():
    """統計 Dashboard 資料。"""
    return jsonify(get_stats(g.db))


@app.route('/api/rescan', methods=['POST'])
def api_rescan():
    """觸發重新掃描。"""
    from scan import scan
    result = scan()
    return jsonify({"ok": True, **(result or {})})


def _migrate_scan_roots():
    """首次啟動遷移：如果 DB 沒有 scan_roots 設定，檢查舊資料推斷。"""
    conn = get_db()
    existing = get_setting(conn, 'scan_roots', '')
    if not existing or existing == '[]':
        # 從現有資料的 filepath 推斷根目錄
        rows = conn.execute(
            "SELECT DISTINCT source FROM doujinshi WHERE source IS NOT NULL"
        ).fetchall()
        if rows:
            # 有舊資料但沒設定 scan_roots，不自動猜測
            # 使用者需要到設定頁面手動新增
            pass
    conn.close()


def _init_thumb_settings():
    """啟動時從 DB 載入縮圖設定。"""
    conn = get_db()
    try:
        _apply_thumb_settings(conn)
    finally:
        conn.close()


if __name__ == '__main__':
    init_db()
    _migrate_scan_roots()
    _init_thumb_settings()
    app.run(debug=config.DEBUG, port=config.PORT)
