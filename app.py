"""同人誌 TAG 搜尋系統 - Flask 應用"""

import os
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, jsonify

from models import (
    get_db, init_db, search_doujinshi, get_doujinshi,
    update_doujinshi, add_tag, remove_tag, get_all_tags, get_filter_options
)
from normalize import find_duplicates_for_field, merge_field_values

app = Flask(__name__)

ALLOWED_ROOTS = ["I:/同人誌", "H:/"]


@app.before_request
def before_request():
    """每個 request 建立 DB 連線。"""
    from flask import g
    g.db = get_db()


@app.teardown_appcontext
def close_db(error):
    from flask import g
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
    from flask import g
    query = request.args.get('q', '')
    event = request.args.get('event', '')
    circle = request.args.get('circle', '')
    author = request.args.get('author', '')
    parody = request.args.get('parody', '')
    tags = request.args.getlist('tags')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
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
    from flask import g
    return jsonify(get_filter_options(g.db))


@app.route('/api/doujinshi/<int:did>')
def api_get(did):
    from flask import g
    item = get_doujinshi(g.db, did)
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@app.route('/api/doujinshi/<int:did>', methods=['PUT'])
def api_update(did):
    from flask import g
    fields = request.get_json()
    update_doujinshi(g.db, did, fields)
    return jsonify(get_doujinshi(g.db, did))


@app.route('/api/doujinshi/<int:did>/tags', methods=['POST'])
def api_add_tag(did):
    from flask import g
    data = request.get_json()
    tag_name = data.get('name', '').strip()
    if not tag_name:
        return jsonify({"error": "tag name required"}), 400
    tag = add_tag(g.db, did, tag_name)
    return jsonify(tag)


@app.route('/api/doujinshi/<int:did>/tags/<int:tid>', methods=['DELETE'])
def api_remove_tag(did, tid):
    from flask import g
    remove_tag(g.db, did, tid)
    return jsonify({"ok": True})


@app.route('/api/tags')
def api_tags():
    from flask import g
    return jsonify(get_all_tags(g.db))


@app.route('/open/<int:did>')
def open_file(did):
    from flask import g
    item = get_doujinshi(g.db, did)
    if not item:
        return jsonify({"error": "not found"}), 404

    filepath = item['filepath']
    # 安全檢查：路徑必須在允許的根目錄下
    norm_path = os.path.normpath(filepath)
    if not any(norm_path.startswith(os.path.normpath(r)) for r in ALLOWED_ROOTS):
        return jsonify({"error": "invalid path"}), 403

    if not os.path.exists(filepath):
        return jsonify({"error": "file not found"}), 404

    os.startfile(filepath)
    return jsonify({"ok": True})


@app.route('/api/doujinshi/<int:did>', methods=['DELETE'])
def api_delete(did):
    """刪除 zip 檔案及 DB 紀錄。僅限 .zip 檔案。"""
    from flask import g
    item = get_doujinshi(g.db, did)
    if not item:
        return jsonify({"error": "not found"}), 404

    filepath = item['filepath']

    # 僅限 zip 檔
    if not filepath.lower().endswith('.zip'):
        return jsonify({"error": "僅限刪除 ZIP 檔案"}), 403

    # 安全檢查：路徑必須在允許的根目錄下
    norm_path = os.path.normpath(filepath)
    if not any(norm_path.startswith(os.path.normpath(r)) for r in ALLOWED_ROOTS):
        return jsonify({"error": "invalid path"}), 403

    # 刪除實體檔案
    if os.path.exists(filepath):
        os.remove(filepath)

    # 刪除 DB 紀錄（含關聯 tags）
    from models import delete_doujinshi
    delete_doujinshi(g.db, did)

    return jsonify({"ok": True, "filename": item['filename']})


@app.route('/api/doujinshi/<int:did>/web-search', methods=['POST'])
def api_web_search(did):
    """觸發 Web 搜尋建議，回傳建議列表（不自動寫入）。"""
    from flask import g
    from web_enrich import enrich_item
    result = enrich_item(g.db, did)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route('/api/doujinshi/<int:did>/apply-suggestion', methods=['POST'])
def api_apply_suggestion(did):
    """使用者確認後寫入選定的建議。"""
    from flask import g
    from web_enrich import apply_suggestion
    suggestion = request.get_json()
    result = apply_suggestion(g.db, did, suggestion)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route('/api/duplicates')
def api_duplicates():
    """偵測指定欄位的重複值。"""
    from flask import g
    field = request.args.get('field', 'parody')
    dupes = find_duplicates_for_field(g.db, field)
    return jsonify(dupes)


@app.route('/api/merge', methods=['POST'])
def api_merge():
    """合併重複值。"""
    from flask import g
    data = request.get_json()
    field = data.get('field', '')
    canonical = data.get('canonical', '')
    old_values = data.get('old_values', [])
    if not field or not canonical or not old_values:
        return jsonify({"error": "missing field, canonical, or old_values"}), 400
    count = merge_field_values(g.db, field, canonical, old_values)
    return jsonify({"ok": True, "updated": count})


@app.route('/api/rescan', methods=['POST'])
def api_rescan():
    """觸發重新掃描。"""
    from scan import scan
    scan()
    return jsonify({"ok": True})


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
