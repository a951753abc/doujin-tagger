/**
 * 自訂 Autocomplete 元件 — fuzzy match + 鍵盤導覽
 * 使用: new AutoComplete(inputEl, { onSelect, maxResults })
 */
class AutoComplete {
    constructor(inputEl, options = {}) {
        this.input = inputEl;
        this.onSelect = options.onSelect || (() => {});
        this.maxResults = options.maxResults || 50;
        this.items = [];
        this.filtered = [];
        this.selectedIndex = -1;
        this.isOpen = false;
        // 偵測是否在 overflow 容器內（如 modal）→ 用 fixed 定位掛到 body
        this.useFixed = !!inputEl.closest('.modal, [style*="overflow"]');

        // 建立 dropdown
        this.dropdown = document.createElement('div');
        this.dropdown.className = 'ac-dropdown';
        this.dropdown.style.display = 'none';
        if (this.useFixed) {
            this.dropdown.style.position = 'fixed';
            document.body.appendChild(this.dropdown);
        } else {
            this.input.parentElement.style.position = 'relative';
            this.input.parentElement.appendChild(this.dropdown);
        }

        this._onInput = this._onInput.bind(this);
        this._onKeydown = this._onKeydown.bind(this);
        this._onBlur = this._onBlur.bind(this);
        this._onDropdownMousedown = this._onDropdownMousedown.bind(this);

        this.input.addEventListener('input', this._onInput);
        this.input.addEventListener('keydown', this._onKeydown);
        this.input.addEventListener('blur', this._onBlur);
        this.input.addEventListener('focus', this._onInput);
        this.dropdown.addEventListener('mousedown', this._onDropdownMousedown);

        // 移除原生 datalist
        this.input.removeAttribute('list');
    }

    setData(items) {
        // items = [{value: string, count: number}]
        this.items = items;
    }

    _onInput() {
        const query = this.input.value.trim().toLowerCase();
        if (!query) {
            this._close();
            return;
        }

        // 先做子字串匹配，再做 fuzzy
        const exact = [];
        const fuzzy = [];

        for (const item of this.items) {
            const val = item.value.toLowerCase();
            if (val.includes(query)) {
                exact.push({ ...item, score: val.indexOf(query) });
            } else if (this._fuzzyMatch(query, val)) {
                fuzzy.push({ ...item, score: 1000 });
            }
        }

        exact.sort((a, b) => a.score - b.score || b.count - a.count);
        fuzzy.sort((a, b) => b.count - a.count);

        this.filtered = [...exact, ...fuzzy].slice(0, this.maxResults);
        this.selectedIndex = -1;
        this._render();
    }

    _fuzzyMatch(query, target) {
        let qi = 0;
        for (let ti = 0; ti < target.length && qi < query.length; ti++) {
            if (target[ti] === query[qi]) qi++;
        }
        return qi === query.length;
    }

    _render() {
        if (this.filtered.length === 0) {
            this._close();
            return;
        }

        this.dropdown.innerHTML = this.filtered.map((item, i) =>
            `<div class="ac-item${i === this.selectedIndex ? ' ac-selected' : ''}" data-index="${i}">
                <span class="ac-value">${this._highlight(item.value, this.input.value.trim())}</span>
                <span class="ac-count">${item.count}</span>
            </div>`
        ).join('');
        if (this.useFixed) {
            const rect = this.input.getBoundingClientRect();
            this.dropdown.style.top = rect.bottom + 4 + 'px';
            this.dropdown.style.left = rect.left + 'px';
            this.dropdown.style.width = rect.width + 'px';
        }
        this.dropdown.style.display = 'block';
        this.isOpen = true;
    }

    _highlight(text, query) {
        if (!query) return this._esc(text);
        const idx = text.toLowerCase().indexOf(query.toLowerCase());
        if (idx === -1) return this._esc(text);
        return this._esc(text.slice(0, idx)) +
            '<mark>' + this._esc(text.slice(idx, idx + query.length)) + '</mark>' +
            this._esc(text.slice(idx + query.length));
    }

    _esc(s) {
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    _onKeydown(e) {
        if (!this.isOpen) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.selectedIndex = Math.min(this.selectedIndex + 1, this.filtered.length - 1);
            this._render();
            this._scrollToSelected();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
            this._render();
            this._scrollToSelected();
        } else if (e.key === 'Enter' && this.selectedIndex >= 0) {
            e.preventDefault();
            this._select(this.selectedIndex);
        } else if (e.key === 'Escape') {
            this._close();
        }
    }

    _scrollToSelected() {
        const el = this.dropdown.querySelector('.ac-selected');
        if (el) el.scrollIntoView({ block: 'nearest' });
    }

    _onDropdownMousedown(e) {
        e.preventDefault(); // 防止 blur
        const item = e.target.closest('.ac-item');
        if (item) this._select(parseInt(item.dataset.index));
    }

    _select(index) {
        const item = this.filtered[index];
        if (!item) return;
        this.input.value = item.value;
        this._close();
        this.onSelect(item);
    }

    _onBlur() {
        setTimeout(() => this._close(), 150);
    }

    _close() {
        this.dropdown.style.display = 'none';
        this.isOpen = false;
        this.selectedIndex = -1;
    }

    destroy() {
        this.input.removeEventListener('input', this._onInput);
        this.input.removeEventListener('keydown', this._onKeydown);
        this.input.removeEventListener('blur', this._onBlur);
        this.input.removeEventListener('focus', this._onInput);
        this.dropdown.remove();
    }
}
