window.EPP = {

  API: '',

  theme: {
    _mq: window.matchMedia('(prefers-color-scheme: dark)'),

    init() {
      const saved  = localStorage.getItem('epp-theme');
      const system = this._mq.matches ? 'dark' : 'light';
      this._apply(saved || system);
      this._mq.addEventListener('change', e => {
        if (!localStorage.getItem('epp-theme')) {
          this._apply(e.matches ? 'dark' : 'light');
        }
      });
    },

    _apply(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      this._updateIcon(theme);
    },

    toggle() {
      const next = this.current() === 'dark' ? 'light' : 'dark';
      this._apply(next);
      localStorage.setItem('epp-theme', next);
    },

    current() {
      return document.documentElement.getAttribute('data-theme') ||
             (this._mq.matches ? 'dark' : 'light');
    },

    _updateIcon(theme) {
      document.querySelectorAll('[data-theme-icon]').forEach(el => {
        el.textContent = theme === 'dark' ? '☀' : '☾';
        el.title = theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
      });
    },
  },

  toast(type, msg, duration = 3500) {
    const container = document.getElementById('toasts');
    if (!container) return;
    const el = document.createElement('div');
    el.className   = `toast ${type}`;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => el.remove(), duration);
  },

  badge(val, type) {
    if (val === null || val === undefined) return `<span class="pill gray">—</span>`;
    return `<span class="pill ${type}">${val}</span>`;
  },

  mono(val) {
    if (val === null || val === undefined) return `<span style="opacity:.4;">—</span>`;
    return `<span style="font-family:var(--mono);font-size:11px;">${val}</span>`;
  },

  renderTable(rows, headId, bodyId, { actions } = {}) {
    const head = document.getElementById(headId);
    const body = document.getElementById(bodyId);
    if (!head || !body) return;
    if (!rows.length) {
      head.innerHTML = '<th>—</th>';
      body.innerHTML = `<tr><td colspan="20" class="tbl-empty">Sin registros</td></tr>`;
      return;
    }
    const cols = Object.keys(rows[0]);
    head.innerHTML = cols.map(c => `<th>${c.toUpperCase()}</th>`).join('') +
      (actions ? '<th>ACCIONES</th>' : '');
    body.innerHTML = rows.map(r => {
      const cells = cols.map(c => {
        const v = r[c];
        if (c === 'is_violation')
          return `<td>${EPP.badge(v ? 'Sí' : 'No', v ? 'danger' : 'ok')}</td>`;
        if (c === 'severity')
          return `<td>${EPP.badge(v, v === 'danger' ? 'danger' : 'warn')}</td>`;
        if (c === 'resolved')
          return `<td>${EPP.badge(v ? 'Resuelto' : 'Pendiente', v ? 'ok' : 'warn')}</td>`;
        if (c === 'source')
          return `<td>${EPP.badge(v, 'info')}</td>`;
        if (c === 'class_name' || c === 'alert_type')
          return `<td>${EPP.badge(v, v?.startsWith('no_') ? 'danger' : 'ok')}</td>`;
        return `<td>${EPP.mono(v)}</td>`;
      }).join('');
      const act = actions ? `<td class="td-actions">${actions(r)}</td>` : '';
      return `<tr>${cells}${act}</tr>`;
    }).join('');
  },

  renderPagination(containerId, { total, current, pageSize, onPageFn }) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const pages = Math.ceil(total / pageSize) || 1;
    const from  = (current - 1) * pageSize + 1;
    const to    = Math.min(current * pageSize, total);
    const btns  = Array.from({ length: Math.min(pages, 8) }, (_, i) =>
      `<button class="page-btn ${i + 1 === current ? 'active' : ''}"
               onclick="${onPageFn}(${i + 1})">${i + 1}</button>`
    ).join('');
    el.innerHTML = btns + `<span class="pag-info">${from}–${to} de ${total}</span>`;
  },

  setHTML(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  },

  setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val ?? '—';
  },

  async apiFetch(url, options = {}) {
    const res = await fetch(EPP.API + url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || res.statusText);
    }
    return res.json();
  },
};

EPP.theme.init();