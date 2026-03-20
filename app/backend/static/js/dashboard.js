// colores hex (RGB) para canvas — equivalentes a los BGR de OpenCV en app.py
const CLASS_COLORS = {
  'persona':       '#0000ff',
  'guante':        '#c80000',
  'no_guante':     '#c86400',
  'gafas':         '#00c800',
  'no_gafas':      '#969600',
  'gorro':         '#c800c8',
  'no_gorro':      '#960096',
  'bata':          '#00c8c8',
  'no_bata':       '#006464',
  'mascarilla':    '#6400c8',
  'no_mascarilla': '#500096',
  'pantalón':      '#ffa500',
  'no_pantalón':   '#c86400',
  'botas':         '#800080',
  'no_botas':      '#500050',
};

// clases cuya ausencia es una violación
const VIOLATION_CLASSES = new Set([
  'no_guante', 'no_gafas', 'no_gorro',
  'no_bata', 'no_mascarilla', 'no_pantalón', 'no_botas',
]);

function getColor(className) {
  return CLASS_COLORS[className] || '#888888';
}

// -- reloj ------------------------------------------------------------------

function updateClock() { EPP.setText('navTime', new Date().toLocaleTimeString('es-MX')); }
updateClock();
setInterval(updateClock, 1000);

// -- navegación -------------------------------------------------------------

function showSection(id, el) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.side-item').forEach(s => s.classList.remove('active'));
  document.getElementById('sec-' + id)?.classList.add('active');
  if (el) el.classList.add('active');
  if (id === 'metricas')  initCharts();
  if (id === 'historial') loadHistorial();
}

// -- opción guardar imágenes ------------------------------------------------

function saveImagesEnabled() {
  return document.getElementById('chkSaveImages')?.checked !== false;
}


// ===========================================================================
// tiempo real
// ===========================================================================

let videoStream     = null;
let videoEl         = null;
let captureInterval = null;
let inferencing     = false;
let rtActive        = false;
let liveDetections  = [];
let alertLog        = [];
let frameCount      = 0;
let fpsTimer        = null;

const CAPTURE_MS = 300;
const CANVAS_W   = 640;
const CANVAS_H   = 360;

async function populateCameraSelector(currentDeviceId) {
  const sel = document.getElementById('cameraSource');
  if (!sel) return;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameras = devices.filter(d => d.kind === 'videoinput');
    sel.innerHTML = cameras.length
      ? cameras.map((c, i) =>
          `<option value="${c.deviceId}" ${c.deviceId === currentDeviceId ? 'selected' : ''}>
            ${c.label || 'Cámara ' + (i + 1)}
          </option>`
        ).join('')
      : '<option value="">Sin cámaras detectadas</option>';
  } catch {
    sel.innerHTML = '<option value="">Error al listar cámaras</option>';
  }
}

async function startCamera() {
  const btn      = document.getElementById('btnPlay');
  const pill     = document.getElementById('livePill');
  const deviceId = document.getElementById('cameraSource')?.value || null;

  if (btn) { btn.textContent = 'Conectando...'; btn.disabled = true; }

  try {
    videoStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width:  { ideal: 1280 },
        height: { ideal: 720  },
        ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: 'environment' }),
      },
      audio: false,
    });

    const trackSettings = videoStream.getVideoTracks()[0]?.getSettings();
    await populateCameraSelector(trackSettings?.deviceId || deviceId);

    if (!videoEl) {
      videoEl = Object.assign(document.createElement('video'), {
        playsInline: true, muted: true,
      });
      videoEl.style.display = 'none';
      document.body.appendChild(videoEl);
    }
    videoEl.srcObject = videoStream;
    await videoEl.play();

    rtActive = true;
    if (btn)  { btn.textContent = '⏹ Detener'; btn.className = 'btn danger'; btn.disabled = false; btn.onclick = stopCamera; }
    if (pill) { pill.textContent = '● EN VIVO'; pill.className = 'rt-pill live'; }
    EPP.setText('rtSourceLabel', 'Cámara activa');

    startCapture();
    startFpsCounter();
    EPP.toast('ok', 'Cámara conectada');

  } catch (err) {
    if (btn) { btn.textContent = '▶ Iniciar cámara'; btn.className = 'btn primary'; btn.disabled = false; btn.onclick = startCamera; }
    const msgs = {
      NotAllowedError:     'Permiso denegado — habilita la cámara en el navegador',
      NotFoundError:       'No se encontró ninguna cámara',
      NotReadableError:    'Cámara en uso por otra aplicación',
      OverconstrainedError:'Cámara seleccionada no compatible',
    };
    EPP.toast('err', msgs[err.name] || `Error: ${err.message}`);
  }
}

function stopCamera() {
  rtActive = false;
  clearInterval(captureInterval); captureInterval = null;
  clearInterval(fpsTimer);

  videoStream?.getTracks().forEach(t => t.stop());
  videoStream = null;
  if (videoEl) videoEl.srcObject = null;

  const btn  = document.getElementById('btnPlay');
  const pill = document.getElementById('livePill');
  if (btn) { btn.textContent = '▶ Iniciar cámara'; btn.className = 'btn primary'; btn.disabled = false; btn.onclick = startCamera; }
  if (pill) { pill.textContent = '⏹ DETENIDO'; pill.className = 'rt-pill info'; }
  EPP.setText('statFps', '—');
  EPP.setText('fpsPill', '— FPS');
  EPP.setText('rtSourceLabel', 'Sin cámara');

  const sel = document.getElementById('cameraSource');
  if (sel) sel.innerHTML = '<option value="">Presiona "Iniciar cámara" para acceder</option>';

  drawIdleCanvas();
  EPP.toast('info', 'Cámara detenida');
}

function startCapture() {
  clearInterval(captureInterval);
  captureInterval = setInterval(async () => {
    if (!rtActive || inferencing || !videoEl || videoEl.readyState < 2) return;
    inferencing = true;
    try {
      const canvas = document.getElementById('rtCanvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(videoEl, 0, 0, CANVAS_W, CANVAS_H);

      const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.80));
      const form = new FormData();
      form.append('image', blob, 'frame.jpg');
      form.append('save_images', saveImagesEnabled() ? 'true' : 'false');
      form.append('source', 'camara');

      const res  = await fetch(`${EPP.API}/api/detect`, { method: 'POST', body: form });
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      ctx.drawImage(videoEl, 0, 0, CANVAS_W, CANVAS_H);

      if (data.warning) {
        drawWarningBanner(ctx, data.warning);
        liveDetections = [];
        renderDetList();
        return;
      }

      drawDetections(ctx, data.detections || []);
      liveDetections = data.detections || [];
      updateRtStats(data);
      renderDetList();
      checkAlerts(data.detections || []);
      frameCount++;
    } catch (err) {
      console.error('Inference error:', err);
    } finally {
      inferencing = false;
    }
  }, CAPTURE_MS);
}

function drawDetections(ctx, detections) {
  detections.forEach(d => {
    const col = getColor(d.class_name);
    const x1  = Math.round(d.x1), y1 = Math.round(d.y1);
    const w   = Math.round(d.x2 - d.x1), h = Math.round(d.y2 - d.y1);

    ctx.strokeStyle = col;
    ctx.lineWidth   = d.is_violation ? 2.5 : 1.8;
    ctx.strokeRect(x1, y1, w, h);
    ctx.fillStyle = col + '22';
    ctx.fillRect(x1, y1, w, h);

    const lbl = `${d.class_name} ${(d.confidence * 100).toFixed(0)}%`;
    ctx.font  = 'bold 11px "Space Mono", monospace';
    const tw  = ctx.measureText(lbl).width;
    ctx.fillStyle = col;
    ctx.fillRect(x1, y1 - 20, tw + 12, 20);
    ctx.fillStyle = '#000';
    ctx.fillText(lbl, x1 + 6, y1 - 5);
  });
}

function drawWarningBanner(ctx, msg) {
  ctx.fillStyle = 'rgba(255,184,48,0.9)';
  ctx.fillRect(0, CANVAS_H - 40, CANVAS_W, 40);
  ctx.fillStyle = '#000';
  ctx.font = 'bold 12px "Space Mono", monospace';
  ctx.textAlign = 'center';
  ctx.fillText('⚠ ' + msg, CANVAS_W / 2, CANVAS_H - 14);
}

function drawIdleCanvas() {
  const canvas = document.getElementById('rtCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#070910';
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
  ctx.strokeStyle = 'rgba(255,255,255,0.03)'; ctx.lineWidth = 1;
  for (let x = 0; x < CANVAS_W; x += 40) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,CANVAS_H); ctx.stroke(); }
  for (let y = 0; y < CANVAS_H; y += 40) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(CANVAS_W,y); ctx.stroke(); }
  ctx.fillStyle = 'rgba(255,255,255,0.18)';
  ctx.font = '14px "Space Mono", monospace'; ctx.textAlign = 'center';
  ctx.fillText('Presiona  ▶ Iniciar cámara  para comenzar', CANVAS_W / 2, CANVAS_H / 2);
  ctx.font = '11px "Space Mono", monospace'; ctx.fillStyle = 'rgba(255,255,255,0.08)';
  ctx.fillText('El permiso se solicitará al iniciar', CANVAS_W / 2, CANVAS_H / 2 + 28);
}

function updateRtStats(data) {
  EPP.setText('statPersonas', data.total_persons || 0);
  EPP.setText('statViol',     data.violations    || 0);
  EPP.setText('statOk',       Math.max(0, (data.total_persons||0) - (data.violations||0)));
}

function startFpsCounter() {
  clearInterval(fpsTimer); frameCount = 0;
  fpsTimer = setInterval(() => {
    EPP.setText('statFps', frameCount);
    EPP.setText('fpsPill', frameCount + ' FPS');
    frameCount = 0;
  }, 1000);
}

function renderDetList() {
  const el = document.getElementById('detList');
  if (!el) return;
  if (!liveDetections.length) {
    el.innerHTML = '<div style="color:var(--text3);text-align:center;padding:20px;font-family:var(--mono);font-size:11px;">Sin detecciones</div>';
    return;
  }
  el.innerHTML = liveDetections.map(d => {
    const col     = getColor(d.class_name);
    const badgeCls = d.is_violation ? 'danger' : d.class_name === 'persona' ? 'info' : 'ok';
    return `<div class="det-item">
      <span class="det-badge ${badgeCls}" style="border-left:3px solid ${col};">${d.class_name}</span>
      <div class="det-info">
        <div class="det-name">bbox [${Math.round(d.x1)},${Math.round(d.y1)},${Math.round(d.x2)},${Math.round(d.y2)}]</div>
        <div class="det-conf">conf: ${(d.confidence*100).toFixed(1)}%</div>
        <div class="conf-bar">
          <div class="conf-fill" style="width:${d.confidence*100}%;background:${col};"></div>
        </div>
      </div></div>`;
  }).join('');
}

function checkAlerts(detections) {
  const viols = detections.filter(d => d.is_violation);
  if (!viols.length) return;
  viols.forEach(v => alertLog.unshift({
    type: v.class_name, time: new Date().toLocaleTimeString('es-MX'), sev: 'danger',
  }));
  if (alertLog.length > 30) alertLog.length = 30;
  renderAlertLog();
  const badge = document.getElementById('alertBadge');
  if (badge) badge.textContent = alertLog.length;
}

function renderAlertLog() {
  const el = document.getElementById('alertList');
  if (!el) return;
  el.innerHTML = alertLog.slice(0, 8).map(a => `
    <div class="alert-item ${a.sev}">
      <div style="font-size:16px;">⚠</div>
      <div style="flex:1;">
        <div class="alert-title">${a.type.replace(/_/g,' ').toUpperCase()}</div>
        <div class="alert-meta">Cámara en vivo</div>
      </div>
      <div class="alert-time">${a.time}</div>
    </div>`).join('');
}


// ===========================================================================
// subir imagen
// ===========================================================================

function handleDrop(e) {
  e.preventDefault();
  document.getElementById('dropzone')?.classList.remove('drag');
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
}

function handleFile(f) {
  if (!f || !f.type.startsWith('image/')) return;
  const reader = new FileReader();
  reader.onload = e => {
    const img = document.getElementById('previewImg');
    if (img) { img.src = e.target.result; img.style.display = 'block'; }
    document.getElementById('previewResult').style.display = 'block';
    EPP.setHTML('uploadResult', '<div style="color:var(--text3);font-family:var(--mono);font-size:11px;text-align:center;padding:30px 0;">Imagen cargada. Presiona Ejecutar detección.</div>');
  };
  reader.readAsDataURL(f);
}

async function runDetection() {
  const input = document.getElementById('fileInput');
  if (!input?.files[0]) { EPP.toast('err', 'Selecciona una imagen primero'); return; }
  const btn = document.getElementById('btnDetect');
  if (btn) { btn.textContent = 'Procesando...'; btn.disabled = true; }
  try {
    const form = new FormData();
    form.append('image', input.files[0]);
    form.append('save_images', saveImagesEnabled() ? 'true' : 'false');
    form.append('source', 'upload');

    const res  = await fetch(`${EPP.API}/api/detect`, { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const img = document.getElementById('previewImg');
    if (img && data.output_image) img.src = data.output_image;

    const dets = data.detections || [];
    EPP.setHTML('uploadResult', dets.length
      ? dets.map(d => {
          const col = getColor(d.class_name);
          return `<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);">
            <span class="pill ${d.is_violation ? 'danger' : d.class_name==='persona' ? 'info' : 'ok'}"
                  style="border-left:3px solid ${col};">${d.class_name}</span>
            <span style="font-family:var(--mono);font-size:11px;color:var(--text2);">conf: ${(d.confidence*100).toFixed(1)}%</span>
            <span style="font-family:var(--mono);font-size:10px;color:var(--text3);margin-left:auto;">[${Math.round(d.x1)},${Math.round(d.y1)},${Math.round(d.x2)},${Math.round(d.y2)}]</span>
          </div>`;
        }).join('')
      : '<div style="color:var(--text3);text-align:center;padding:20px;font-family:var(--mono);">Sin detecciones</div>'
    );

    EPP.setHTML('uploadSummary', `
      <div style="display:flex;gap:20px;justify-content:center;">
        <div style="text-align:center;"><div style="font-family:var(--mono);font-size:24px;color:var(--blue);">${data.total_persons}</div><div style="font-size:11px;color:var(--text3);margin-top:2px;">Personas</div></div>
        <div style="text-align:center;"><div style="font-family:var(--mono);font-size:24px;color:var(--ok);">${dets.filter(d=>!d.is_violation&&d.class_name!=='persona').length}</div><div style="font-size:11px;color:var(--text3);margin-top:2px;">EPP OK</div></div>
        <div style="text-align:center;"><div style="font-family:var(--mono);font-size:24px;color:var(--danger);">${data.violations}</div><div style="font-size:11px;color:var(--text3);margin-top:2px;">Violaciones</div></div>
        <div style="text-align:center;"><div style="font-family:var(--mono);font-size:24px;color:var(--text2);">${data.duration_ms}ms</div><div style="font-size:11px;color:var(--text3);margin-top:2px;">Duración</div></div>
      </div>`);

    const saveNote = data.saved_images ? '' : ' <span style="color:var(--warn);font-size:10px;font-family:var(--mono);">(sin guardar en disco)</span>';
    EPP.toast('ok', `Sesión #${data.session_id} guardada${saveNote ? ' — imágenes no guardadas' : ''}`);
  } catch (err) {
    EPP.toast('err', `Error: ${err.message}`);
  } finally {
    if (btn) { btn.textContent = 'Ejecutar detección'; btn.disabled = false; }
  }
}

function clearUpload() {
  const input = document.getElementById('fileInput');
  if (input) input.value = '';
  const img = document.getElementById('previewImg');
  if (img) { img.src = ''; img.style.display = 'none'; }
  const pr = document.getElementById('previewResult');
  if (pr) pr.style.display = 'none';
}


// ===========================================================================
// historial
// ===========================================================================

let histPage = 1;
const HIST_PS = 15;

function goHistPage(p) { histPage = p; loadHistorial(); }

async function loadHistorial() {
  const tabla   = document.getElementById('filtTabla')?.value  || 'detections';
  const clase   = document.getElementById('filtClase')?.value  || '';
  const estado  = document.getElementById('filtEstado')?.value || '';
  const modelo  = document.getElementById('filtModelo')?.value || '';
  const confMin = document.getElementById('filtConf')?.value   || 0;

  const params = new URLSearchParams({ tabla, limite: HIST_PS, pagina: histPage });
  if (clase)   params.set('clase',    clase);
  if (estado)  params.set('estado',   estado);
  if (modelo)  params.set('modelo',   modelo);
  if (confMin) params.set('conf_min', confMin);

  try {
    const data = await EPP.apiFetch(`/api/historial?${params}`);
    EPP.renderTable(data.data || [], 'histHead', 'histBody');
    EPP.renderPagination('histPag', {
      total: data.total, current: histPage, pageSize: HIST_PS, onPageFn: 'goHistPage',
    });
    EPP.setText('histSubtitle', `${tabla} · ${data.total} registros`);
  } catch {
    EPP.toast('err', 'Error cargando historial');
  }
}

async function exportHistCSV() {
  const tabla = document.getElementById('filtTabla')?.value || 'detections';
  try {
    const data = await EPP.apiFetch(`/api/historial?tabla=${tabla}&limite=500`);
    const rows = data.data || [];
    if (!rows.length) { EPP.toast('err', 'Sin datos'); return; }
    const cols = Object.keys(rows[0]);
    const csv  = [cols.join(','), ...rows.map(r => cols.map(c => JSON.stringify(r[c]??'')).join(','))].join('\n');
    const a    = document.createElement('a');
    a.href     = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
    a.download = `${tabla}_epp.csv`;
    a.click();
    EPP.toast('ok', 'CSV exportado');
  } catch { EPP.toast('err', 'Error exportando CSV'); }
}


// ===========================================================================
// métricas
// ===========================================================================

let chartsInited = false;

async function initCharts() {
  if (chartsInited) return;
  chartsInited = true;

  try {
    const s = await EPP.apiFetch('/api/stats');
    EPP.setText('mTotalDet',  s.total_detections);
    EPP.setText('mTotalSes',  s.total_sessions);
    EPP.setText('mTotalViol', s.total_violations);
    EPP.setText('mAvgConf',   s.avg_confidence);
  } catch { /* sin datos aún */ }

  try {
    const m = await EPP.apiFetch('/api/metricas?model_id=2');
    if (!m.epocas?.length) return;

    const gc = 'rgba(255,255,255,0.05)', tc = '#50556a';
    const base = {
      responsive: true, maintainAspectRatio: true,
      plugins: { legend: { labels: { color: '#8a8fa8', font: { family:"'Space Mono',monospace", size: 10 } } } },
      scales: {
        x: { grid: { color: gc }, ticks: { color: tc, font: { family:"'Space Mono',monospace", size: 9 } } },
        y: { grid: { color: gc }, ticks: { color: tc, font: { family:"'Space Mono',monospace", size: 9 } } },
      },
    };
    const ds = (label, data, color) => ({
      label, data, borderColor: color, backgroundColor: color + '10',
      tension: .4, pointRadius: 3, borderWidth: 2,
    });

    new Chart(document.getElementById('chartMap'),  { type:'line', options:base, data:{ labels:m.epocas, datasets:[ds('mAP50',m.map50,'#00e5a0')] }});
    new Chart(document.getElementById('chartLoss'), { type:'line', options:base, data:{ labels:m.epocas, datasets:[ds('box_loss',m.box_loss,'#ff4d6d'),ds('cls_loss',m.cls_loss,'#ffb830'),ds('dfl_loss',m.dfl_loss,'#7f77dd')] }});
    new Chart(document.getElementById('chartPR'),   { type:'line', options:base, data:{ labels:m.epocas, datasets:[ds('Precision',m.precision,'#00e5a0'),ds('Recall',m.recall,'#0096ff')] }});
  } catch (e) { console.error('Charts error:', e); }

  try {
    const dets    = await EPP.apiFetch('/api/detections?limite=500&pagina=1');
    const clases  = {};
    (dets.data||[]).forEach(d => { clases[d.class_name] = (clases[d.class_name]||0)+1; });
    const labels  = Object.keys(clases);
    const valores = Object.values(clases);
    const colores = labels.map(l => CLASS_COLORS[l] || '#888888');
    new Chart(document.getElementById('chartClases'), {
      type: 'bar',
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#50556a', font: { family:"'Space Mono',monospace", size: 9 } } },
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#50556a', font: { family:"'Space Mono',monospace", size: 9 } } },
        },
      },
      data: {
        labels,
        datasets: [{ label:'Detecciones', data:valores, backgroundColor:colores.map(c=>c+'28'), borderColor:colores, borderWidth:2, borderRadius:4 }],
      },
    });
  } catch (e) { console.error('chartClases error:', e); }
}


// ===========================================================================
// configuración
// ===========================================================================

async function loadConfig() {
  try {
    const resp = await EPP.apiFetch('/api/config');
    const cfgs = Array.isArray(resp) ? resp : (resp.data || []);
    cfgs.forEach(cfg => {
      const cs = document.getElementById(`conf_${cfg.id}`), cv = document.getElementById(`confVal_${cfg.id}`);
      const is = document.getElementById(`iou_${cfg.id}`),  iv = document.getElementById(`iouVal_${cfg.id}`);
      if (cs) { cs.value = cfg.conf_threshold; if (cv) cv.textContent = cfg.conf_threshold; }
      if (is) { is.value = cfg.iou_threshold;  if (iv) iv.textContent = cfg.iou_threshold; }
    });
  } catch (e) { console.error('loadConfig:', e); }
}

async function saveConfig(id) {
  const conf = parseFloat(document.getElementById(`conf_${id}`)?.value || 0);
  const iou  = parseFloat(document.getElementById(`iou_${id}`)?.value  || 0);
  try {
    await EPP.apiFetch(`/api/config/${id}`, { method:'PUT', body:JSON.stringify({ conf_threshold:conf, iou_threshold:iou }) });
    EPP.toast('ok', 'Configuración guardada');
  } catch { EPP.toast('err', 'Error guardando config'); }
}


// ===========================================================================
// init
// ===========================================================================

document.addEventListener('DOMContentLoaded', () => {
  const sel = document.getElementById('cameraSource');
  if (sel) sel.innerHTML = '<option value="">Presiona "Iniciar cámara" para acceder</option>';

  loadConfig();
  drawIdleCanvas();
});