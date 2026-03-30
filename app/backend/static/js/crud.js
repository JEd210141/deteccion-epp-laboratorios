const PAGE_SIZE = 20;

const state = {
  tabla:   'detections',
  pagina:  1,
  total:   0,
  editId:  null,
  filtros: {},
};

function goPage(p) { state.pagina = p; loadTabla(); }

function dbToast(type, msg, duration = 3500) {
  const container = document.getElementById('toasts');
  if (!container) return;
  const el = document.createElement('div');
  el.className   = `db-toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

function switchTabla(tabla, el) {
  state.tabla   = tabla;
  state.pagina  = 1;
  state.editId  = null;
  state.filtros = {};

  document.querySelectorAll('.db-tab, .db-side-item').forEach(b => b.classList.remove('active'));
  if (el) {
    const attr = el.dataset.tabla;
    document.querySelectorAll(`[data-tabla="${attr}"]`).forEach(b => b.classList.add('active'));
  }

  renderFiltros(tabla);
  loadTabla();
  hideForm();
  updateSqlBreadcrumb(tabla);
}

function updateSqlBreadcrumb(tabla) {
  const el = document.getElementById('sqlBreadcrumb');
  if (el) el.innerHTML = `<span class="op">SELECT</span> * <span class="op">FROM</span> <span class="seg">${tabla}</span>`;
}

// Filtros dinámicos
const FILTROS_CONFIG = {
  detections: [
    { id:'f_clase',  type:'select',
      options:['','persona','guante','no_guante','gafas','no_gafas','gorro','no_gorro',
               'bata','no_bata','mascarilla','no_mascarilla','pantalón','no_pantalón','botas','no_botas'],
      label:'Clase' },
    { id:'f_estado', type:'select', options:['','ok','viol'], labels:['Estado','Sin violación','Con violación'], label:'Estado' },
    { id:'f_modelo', type:'select', options:['','yolo26m','modeloepp_v1'], label:'Modelo' },
    { id:'f_conf',   type:'number', placeholder:'Conf. mín.', step:'0.1', label:'Conf. mín.' },
  ],
  sessions:         [{ id:'f_source',   type:'select', options:['','upload','camara'], label:'Fuente' }],
  alerts:           [
    { id:'f_resolved', type:'select', options:['','false','true'], labels:['Estado','Pendientes','Resueltas'], label:'Estado' },
    { id:'f_severity', type:'select', options:['','danger','warn'], label:'Severidad' },
  ],
  training_metrics: [{ id:'f_model_id', type:'select', options:['','1','2'], labels:['Modelo','yolo26m (1)','modeloepp_v1 (2)'], label:'Modelo' }],
  model_config: [],
};

function renderFiltros(tabla) {
  const cfg  = FILTROS_CONFIG[tabla] || [];
  const wrap = document.getElementById('filtrosWrap');
  if (!wrap) return;
  if (!cfg.length) {
    wrap.innerHTML = '<span class="db-filter-label">Sin filtros disponibles</span>';
    return;
  }
  wrap.innerHTML = '<span class="db-filter-label">WHERE</span>' + cfg.map(f => {
    if (f.type === 'select') {
      const opts = f.options.map((v, i) =>
        `<option value="${v}">${f.labels ? f.labels[i] : (v || f.label)}</option>`
      ).join('');
      return `<select class="db-inp" id="${f.id}" onchange="applyFiltros()">${opts}</select>`;
    }
    return `<input class="db-inp" id="${f.id}" type="number" placeholder="${f.label}" step="${f.step||'0.01'}" oninput="applyFiltros()"/>`;
  }).join('') + `<button class="db-btn" onclick="clearFiltros()">✕</button>`;
}

function applyFiltros() {
  state.pagina = 1; state.filtros = {};
  (FILTROS_CONFIG[state.tabla]||[]).forEach(f => {
    const val = document.getElementById(f.id)?.value;
    if (val) state.filtros[f.id.replace('f_','')] = val;
  });
  loadTabla();
}

function clearFiltros() {
  (FILTROS_CONFIG[state.tabla]||[]).forEach(f => {
    const el = document.getElementById(f.id);
    if (el) el.value = '';
  });
  state.filtros = {}; state.pagina = 1; loadTabla();
}

// Endpoints
const ENDPOINT = {
  detections:       '/api/detections',
  sessions:         '/api/sessions',
  alerts:           '/api/alerts',
  training_metrics: '/api/metrics',
  model_config:     '/api/models',
};

async function loadTabla() {
  const ep     = ENDPOINT[state.tabla];
  const params = new URLSearchParams({ pagina:state.pagina, limite:PAGE_SIZE, ...state.filtros });
  const tbody = document.getElementById('tblBody');
  const thead = document.getElementById('tblHead');
  if (tbody) tbody.innerHTML = `<tr class="db-loading-row"><td colspan="20"><div class="db-loading"></div> Consultando MariaDB...</td></tr>`;
  try {
    const data = await EPP.apiFetch(`${ep}?${params}`);
    const rows = data.data || [];
    state.total = data.total ?? rows.length;
    updateStatusBar(state.total);
    renderDbTable(rows, thead, tbody);
    renderDbPagination(state.total, state.pagina);
    updateSideCount(state.tabla, state.total);
  } catch (e) {
    if (tbody) tbody.innerHTML = `<tr class="db-loading-row"><td colspan="20" style="color:var(--db-red);">⚠ ${e.message}</td></tr>`;
    dbToast('err', `Error MariaDB: ${e.message}`);
  }
}

function renderDbTable(rows, thead, tbody) {
  if (!rows.length) {
    if (thead) thead.innerHTML = '<th>—</th>';
    if (tbody) tbody.innerHTML = `<tr><td colspan="20"><div class="db-empty"><div class="db-empty-icon">⊘</div>Sin registros en ${state.tabla}</div></td></tr>`;
    return;
  }
  const cols = Object.keys(rows[0]);
  if (thead) thead.innerHTML = cols.map(c => `<th>${c.toUpperCase()}</th>`).join('') + '<th>ACTIONS</th>';
  if (tbody) tbody.innerHTML = rows.map(r => {
    const cells = cols.map(c => {
      const v = r[c];
      if (c === 'is_violation') return `<td>${v ? '<span class="db-pill danger">VIOL</span>' : '<span class="db-pill ok">OK</span>'}</td>`;
      if (c === 'severity')     return `<td><span class="db-pill ${v==='danger'?'danger':'warn'}">${v||'—'}</span></td>`;
      if (c === 'resolved')     return `<td><span class="db-pill ${v?'ok':'warn'}">${v?'Resuelto':'Pendiente'}</span></td>`;
      if (c === 'source')       return `<td><span class="db-pill info">${v||'—'}</span></td>`;
      if (c === 'class_name' || c === 'alert_type') return `<td><span class="db-pill ${v?.startsWith('no_')?'danger':'ok'}">${v||'—'}</span></td>`;
      if (v === null || v === undefined) return `<td><span class="db-null">NULL</span></td>`;
      if (typeof v === 'number') return `<td><span class="db-num">${v}</span></td>`;
      return `<td style="font-family:var(--db-mono);font-size:11px;">${v}</td>`;
    }).join('');
    return `<tr>${cells}<td class="td-actions">
      <button class="db-btn edit" onclick="openEdit(${r.id})">Edit</button>
      <button class="db-btn del"  onclick="confirmDelete(${r.id},'${r.class_name||r.name||r.alert_type||r.epoch||r.source||''}')">Del</button>
    </td></tr>`;
  }).join('');
}

function renderDbPagination(total, current) {
  const pages = Math.ceil(total / PAGE_SIZE) || 1;
  const from  = (current - 1) * PAGE_SIZE + 1;
  const to    = Math.min(current * PAGE_SIZE, total);
  const btns  = Array.from({ length: Math.min(pages, 8) }, (_, i) =>
    `<button class="db-page-btn ${i+1===current?'active':''}" onclick="goPage(${i+1})">${i+1}</button>`
  ).join('');
  EPP.setHTML('paginacion', btns + `<span class="db-pag-info">${from}–${to} / ${total}</span>`);
}

function updateStatusBar(total) {
  EPP.setText('statusRows', total + ' rows');
  EPP.setText('statusTable', state.tabla);
  EPP.setText('statusPage', `p.${state.pagina}`);
}

function updateSideCount(tabla, total) {
  const el = document.querySelector(`.db-side-item[data-tabla="${tabla}"] .db-row-count`);
  if (el) el.textContent = total;
}

// Formulario
const FORM_FIELDS = {
  detections: [
    { id:'session_id',   label:'session_id *',  type:'number', required:true },
    { id:'model_used',   label:'model_used *',  type:'select', options:['','yolo26m','modeloepp_v1'], required:true },
    { id:'class_name',   label:'class_name *',  type:'select',
      options:['','persona','guante','no_guante','gafas','no_gafas','gorro','no_gorro',
               'bata','no_bata','mascarilla','no_mascarilla','pantalón','no_pantalón','botas','no_botas'],
      required:true },
    { id:'confidence',   label:'confidence *',  type:'number', step:'0.001', min:'0', max:'1', required:true },
    { id:'is_violation', label:'is_violation',  type:'select', options:['0','1'], labels:['No (EPP OK)','Sí (violación)'] },
    { id:'x1', label:'x1', type:'number' }, { id:'y1', label:'y1', type:'number' },
    { id:'x2', label:'x2', type:'number' }, { id:'y2', label:'y2', type:'number' },
    { id:'person_id', label:'person_id', type:'number' },
  ],
  sessions: [
    { id:'source',        label:'source *',      type:'select', options:['','upload','camara'], required:true },
    { id:'image_path',    label:'image_path',    type:'text',   placeholder:'static/uploads/...' },
    { id:'output_path',   label:'output_path',   type:'text',   placeholder:'static/outputs/...' },
    { id:'duration_ms',   label:'duration_ms',   type:'number' },
    { id:'total_persons', label:'total_persons', type:'number' },
    { id:'total_epp_ok',  label:'total_epp_ok',  type:'number' },
  ],
  alerts: [
    { id:'session_id', label:'session_id *', type:'number', required:true },
    { id:'alert_type', label:'alert_type *', type:'select',
      options:['','no_guante','no_gafas','no_gorro','no_bata','no_mascarilla','no_pantalón','no_botas'],
      required:true },
    { id:'severity',   label:'severity',     type:'select', options:['danger','warn'] },
    { id:'resolved',   label:'resolved',     type:'select', options:['0','1'], labels:['Pendiente','Resuelto'] },
    { id:'notes',      label:'notes',        type:'textarea', full:true },
  ],
  training_metrics: [
    { id:'model_id',  label:'model_id *', type:'select', options:['1','2'], labels:['1 — yolo26m','2 — modeloepp_v1'], required:true },
    { id:'epoch',     label:'epoch *',    type:'number', required:true },
    { id:'box_loss',  label:'box_loss *', type:'number', step:'0.001', required:true },
    { id:'cls_loss',  label:'cls_loss *', type:'number', step:'0.001', required:true },
    { id:'dfl_loss',  label:'dfl_loss',   type:'number', step:'0.001' },
    { id:'precision', label:'precision',  type:'number', step:'0.001', min:'0', max:'1' },
    { id:'recall',    label:'recall',     type:'number', step:'0.001', min:'0', max:'1' },
    { id:'map50',     label:'map50',      type:'number', step:'0.0001', min:'0', max:'1' },
    { id:'map50_95',  label:'map50_95',   type:'number', step:'0.0001', min:'0', max:'1' },
  ],
  model_config: [
    { id:'name',           label:'name *',         type:'text', required:true },
    { id:'weights_path',   label:'weights_path',   type:'text', placeholder:'models/modelo.pt' },
    { id:'conf_threshold', label:'conf_threshold', type:'number', step:'0.05', min:'0.05', max:'0.95' },
    { id:'iou_threshold',  label:'iou_threshold',  type:'number', step:'0.05', min:'0.05', max:'0.95' },
    { id:'img_size',       label:'img_size',        type:'number' },
  ],
};

function openCreate() { state.editId = null; renderForm(state.tabla, null); showForm(false); }

async function openEdit(id) {
  const ep = ENDPOINT[state.tabla];
  try {
    const data = await EPP.apiFetch(`${ep}/${id}`);
    state.editId = id;
    renderForm(state.tabla, data);
    showForm(true);
  } catch (e) { dbToast('err', `Error cargando #${id}: ${e.message}`); }
}

function renderForm(tabla, data) {
  const fields = FORM_FIELDS[tabla] || [];
  let html = '<div class="db-form-grid">';
  fields.forEach(f => {
    const val  = data ? (data[f.id] ?? '') : '';
    const full = f.full || f.type === 'textarea' ? 'db-form-full' : '';
    if (f.type === 'select') {
      const opts = f.options.map((o, i) =>
        `<option value="${o}" ${String(val)===String(o)?'selected':''}>${f.labels?f.labels[i]:(o||'— seleccionar —')}</option>`
      ).join('');
      html += `<div class="db-form-group ${full}">
        <label class="db-form-label">${f.label}</label>
        <select class="db-inp" id="frm_${f.id}" onchange="updateSqlPreview()">${opts}</select>
      </div>`;
    } else if (f.type === 'textarea') {
      html += `<div class="db-form-group db-form-full">
        <label class="db-form-label">${f.label}</label>
        <textarea class="db-inp" id="frm_${f.id}" rows="3" oninput="updateSqlPreview()">${val}</textarea>
      </div>`;
    } else {
      const attrs = [f.step?`step="${f.step}"`:'', f.min?`min="${f.min}"`:'', f.max?`max="${f.max}"`:'', f.placeholder?`placeholder="${f.placeholder}"`:''].filter(Boolean).join(' ');
      html += `<div class="db-form-group">
        <label class="db-form-label">${f.label}</label>
        <input class="db-inp" id="frm_${f.id}" type="${f.type}" value="${val}" ${attrs} oninput="updateSqlPreview()"/>
      </div>`;
    }
  });
  html += '</div>';
  EPP.setHTML('formFields', html);
  updateSqlPreview();
}

function getFormPayload() {
  const fields = FORM_FIELDS[state.tabla] || [];
  const payload = {};
  fields.forEach(f => {
    const el = document.getElementById(`frm_${f.id}`);
    if (!el) return;
    if (f.type === 'number') {
      const v = parseFloat(el.value);
      payload[f.id] = isNaN(v) ? null : v;
    } else {
      payload[f.id] = el.value || null;
    }
  });
  return payload;
}

function updateSqlPreview() {
  const p      = getFormPayload();
  const isEdit = state.editId !== null;
  const nonNull = Object.entries(p).filter(([,v]) => v !== null);
  let sql = '';
  if (isEdit) {
    const sets = nonNull.map(([k,v]) =>
      `<span style="color:var(--db-primary)">${k}</span>=<span style="color:var(--db-amber)">${JSON.stringify(v)}</span>`
    ).join(', ');
    sql = `<span style="color:var(--db-cyan)">UPDATE</span> ${state.tabla} <span style="color:var(--db-cyan)">SET</span> ${sets} <span style="color:var(--db-cyan)">WHERE</span> id=${state.editId}`;
  } else {
    const cols = nonNull.map(([k]) => `<span style="color:var(--db-primary)">${k}</span>`).join(', ');
    const vals = nonNull.map(([,v]) => `<span style="color:var(--db-amber)">${JSON.stringify(v)}</span>`).join(', ');
    sql = `<span style="color:var(--db-cyan)">INSERT INTO</span> ${state.tabla} (${cols}) <span style="color:var(--db-cyan)">VALUES</span> (${vals})`;
  }
  EPP.setHTML('sqlPreview', sql);
}

function showForm(isEdit) {
  const panel = document.getElementById('formPanel');
  const title = document.getElementById('formTitle');
  if (!panel) return;
  panel.style.display = 'block';
  if (title) {
    title.className = 'db-form-title' + (isEdit ? ' editing' : '');
    title.innerHTML = isEdit
      ? `<strong>${state.tabla}</strong> &nbsp;·&nbsp; <span style="opacity:.6;">id = ${state.editId}</span>`
      : `<strong>${state.tabla}</strong>`;
  }
  panel.scrollIntoView({ behavior:'smooth', block:'nearest' });
}

function hideForm() {
  const panel = document.getElementById('formPanel');
  if (panel) panel.style.display = 'none';
  state.editId = null;
}

async function submitForm() {
  const fields   = FORM_FIELDS[state.tabla] || [];
  const required = fields.filter(f => f.required).map(f => `frm_${f.id}`);
  let valid = true;
  required.forEach(id => {
    const el = document.getElementById(id);
    if (!el?.value) { el?.classList.add('err'); valid = false; }
    else             el?.classList.remove('err');
  });
  if (!valid) { dbToast('err', 'Completa los campos obligatorios (*)'); return; }
  const ep      = ENDPOINT[state.tabla];
  const payload = getFormPayload();
  const isEdit  = state.editId !== null;
  const url     = isEdit ? `${ep}/${state.editId}` : ep;
  try {
    const data = await EPP.apiFetch(url, { method:isEdit?'PUT':'POST', body:JSON.stringify(payload) });
    if (data.error) throw new Error(data.error);
    dbToast('ok', isEdit ? `#${state.editId} actualizado` : `#${data.id} insertado en ${state.tabla}`);
    hideForm();
    loadTabla();
    loadStats();
  } catch (e) { dbToast('err', `Error: ${e.message}`); }
}

function confirmDelete(id, label) {
  const modal = document.getElementById('deleteModal');
  if (!modal) return;
  EPP.setHTML('deleteLabel',
    `<span style="color:var(--db-primary)">DELETE FROM</span> ${state.tabla} ` +
    `<span style="color:var(--db-cyan)">WHERE</span> id = ` +
    `<span style="color:var(--db-amber)">${id}</span> ` +
    `<span style="color:var(--db-text3)">-- ${label}</span>`
  );
  modal.style.display = 'flex';
  modal.dataset.id    = id;
}

function cancelDelete() { const modal = document.getElementById('deleteModal'); if (modal) modal.style.display = 'none'; }

async function executeDelete() {
  const modal = document.getElementById('deleteModal');
  const id    = modal?.dataset.id;
  const ep    = ENDPOINT[state.tabla];
  cancelDelete();
  try {
    const data = await EPP.apiFetch(`${ep}/${id}`, { method:'DELETE' });
    if (data.error) throw new Error(data.error);
    dbToast('ok', `#${id} eliminado de ${state.tabla}`);
    loadTabla();
    loadStats();
  } catch (e) { dbToast('err', `Error: ${e.message}`); }
}

async function loadStats() {
  try {
    const s = await EPP.apiFetch('/api/stats');
    EPP.setText('stTotalDet',   s.total_detections);
    EPP.setText('stTotalSes',   s.total_sessions);
    EPP.setText('stTotalViol',  s.total_violations);
    EPP.setText('stAvgConf',    s.avg_confidence);
    EPP.setText('stAlerts',     s.total_alerts);
    EPP.setText('stUnresolved', s.unresolved_alerts);
  } catch { /* silencioso */ }
}

async function exportCSV() {
  const ep = ENDPOINT[state.tabla];
  try {
    const data = await EPP.apiFetch(`${ep}?limite=1000&pagina=1`);
    const rows = data.data || [];
    if (!rows.length) { dbToast('err', 'Sin datos para exportar'); return; }
    const cols = Object.keys(rows[0]);
    const csv  = [cols.join(','), ...rows.map(r => cols.map(c => JSON.stringify(r[c]??'')).join(','))].join('\n');
    const a    = document.createElement('a');
    a.href     = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
    a.download = `${state.tabla}.csv`;
    a.click();
    dbToast('ok', `${state.tabla}.csv exportado`);
  } catch { dbToast('err', 'Error exportando CSV'); }
}

document.addEventListener('DOMContentLoaded', () => {
  renderFiltros('detections');
  updateSqlBreadcrumb('detections');
  loadTabla();
  loadStats();
});