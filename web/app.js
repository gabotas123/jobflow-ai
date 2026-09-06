/* JobFlow AI - logica de la SPA (multi-perfil) */
const api = async (path, opts = {}) => {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) throw new Error((await res.text()).slice(0, 300));
  return res.json();
};
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const SALARY_OPTIONS = ['S/1400 - S/1800', 'S/1800 - S/2300', 'S/2300 - S/2500',
  'S/2500 - S/2800', 'S/2800 - S/3200', 'S/3200 - S/4000', 'S/4000+', '(por definir)'];

let profiles = [];
let activeId = null;
let formState = null;
let puestosCache = [];
let activePuestoId = null;

document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

function goTab(name) {
  const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
  if (btn) btn.click();
}

function salaryOptions(selected) {
  const opts = new Set(SALARY_OPTIONS);
  if (selected && !opts.has(selected)) opts.add(selected);
  return `<option value="">— elegir rango —</option>` + [...opts].map((s) =>
    `<option ${s === selected ? 'selected' : ''} value="${esc(s)}">${esc(s)}</option>`).join('');
}

/* ---------------- Perfiles ---------------- */
async function loadProfiles() {
  profiles = await api('/api/profiles');
  const saved = Number(localStorage.getItem('jobflow_active_profile'));
  if (profiles.some((p) => p.id === saved)) activeId = saved;
  else activeId = profiles.length ? profiles[0].id : null;
  renderProfileList();
  if (activeId) { loadDashboard(); loadProfileDetail(activeId); loadPuestos(activeId); }
}

function renderProfileList() {
  document.getElementById('profiles-list').innerHTML = (profiles || []).map((p) => `
    <div class="profile-card ${p.id === activeId ? 'active' : ''}">
      <b>${esc(p.nombre)}</b>
      <span class="profile-meta">${esc(p.fuente_cv)} ${p.verificado ? '· <span class="badge ok">VERIFICADO</span>' : ''}</span>
      <span style="flex:1"></span>
      <button class="btn ${p.id === activeId ? 'primary' : ''}" onclick="selectProfile(${p.id})">Usar</button>
      <button class="btn" onclick="loadProfileDetail(${p.id})">Detalle</button>
    </div>`).join('') || '<p class="muted">Sin perfiles. Sube un CV en la sección superior.</p>';
}

function selectProfile(id) {
  activeId = id;
  localStorage.setItem('jobflow_active_profile', id);
  renderProfileList();
  loadDashboard();
  loadProfileDetail(id);
  loadPuestos(id);
}

async function uploadCV() {
  const file = document.getElementById('upload-file').files[0];
  const nombre = document.getElementById('upload-name').value;
  const status = document.getElementById('upload-status');
  if (!file) { status.innerHTML = '<p style="color:var(--warn)">Elige un archivo (PDF/DOCX/TXT).</p>'; return; }
  status.innerHTML = '<p>Procesando CV…</p>';
  try {
    const fd = new FormData();
    fd.append('file', file);
    if (nombre) fd.append('nombre_hint', nombre);
    const res = await fetch('/api/cv/upload', { method: 'POST', body: fd });
    if (!res.ok) throw new Error((await res.text()).slice(0, 300));
    const data = await res.json();
    status.innerHTML = `<p style="color:var(--ok)">✔ CV procesado: <b>${esc(data.nombre)}</b> · ${data.experiencia.length} puesto(s) · ${data.skills.length} habilidades</p>`;
    await loadProfiles();
    selectProfile(data.id);
  } catch (e) {
    status.innerHTML = `<p style="color:var(--bad)">Error: ${esc(e.message)}</p>`;
  }
}

async function loadProfileDetail(id) {
  try {
    const p = await api('/api/profiles/' + id);
    document.getElementById('profile-detail').innerHTML = `
      <div class="card">
        <h2>Datos del candidato — ${esc(p.nombre)} <small class="muted">(${esc(p.fuente_cv)})</small></h2>
        <div class="detail-grid">
          <label>Nombre<input id="pf-nombre" value="${esc(p.nombre)}"></label>
          <label>Email<input id="pf-email" value="${esc(p.email)}"></label>
          <label>Teléfono<input id="pf-telefono" value="${esc(p.telefono)}"></label>
          <label>Ubicación<input id="pf-ubicacion" value="${esc(p.ubicacion)}"></label>
          <label>LinkedIn<input id="pf-linkedin" value="${esc(p.linkedin)}"></label>
          <label>Seniority<select id="pf-seniority">
            ${['asistente', 'analista_junior', 'analista'].map((s) => `<option ${p.seniority === s ? 'selected' : ''}>${s}</option>`).join('')}
          </select></label>
          <label>Rango salarial (elegible)
            <select id="pf-salario">${salaryOptions(p.rango_salarial)}</select>
          </label>
          <label>Disponibilidad<input id="pf-disp" value="${esc(p.disponibilidad)}"></label>
          <label>Movilidad<input id="pf-mov" value="${esc(p.movilidad)}"></label>
        </div>
        <div class="detail-grid">
          <label>Headline / cargo deseado<input id="pf-headline" value="${esc(p.headline)}"></label>
          <label>Resumen (perfil)<textarea id="pf-summary">${esc(p.summary)}</textarea></label>
        </div>
        <h3 style="margin-top:14px">Experiencia detectada</h3>
        ${(p.experiencia || []).map((e) => `<pre>${esc(e.cargo)} · ${esc(e.empresa)} (${esc(e.inicio)} - ${esc(e.fin)})
  ${esc((e.bullets || []).slice(0, 3).join('\n  '))}</pre>`).join('') || '<p class="muted">Sin experiencia detectada.</p>'}
        <div class="hint">⚠ Los campos vacíos son datos que no se detectaron: complétalos o se marcarán
          para confirmación (la app nunca inventa respuestas).</div>
        <button class="btn primary" onclick="saveProfile(${id})">💾 Guardar cambios</button>
        <button class="btn" onclick="generateCV(${id})">✨ Generar CV corregido (descargar)</button>
        <div id="pf-status"></div>
        ${p.texto_extraido ? `<details><summary>Texto extraído del CV</summary><pre>${esc(p.texto_extraido)}</pre></details>` : ''}
      </div>`;
  } catch (e) {
    document.getElementById('profile-detail').innerHTML = `<div class="card" style="color:var(--bad)">Error: ${esc(e.message)}</div>`;
  }
}

async function saveProfile(id) {
  const body = {
    nombre: document.getElementById('pf-nombre').value,
    email: document.getElementById('pf-email').value,
    telefono: document.getElementById('pf-telefono').value,
    ubicacion: document.getElementById('pf-ubicacion').value,
    linkedin: document.getElementById('pf-linkedin').value,
    seniority: document.getElementById('pf-seniority').value,
    rango_salarial: document.getElementById('pf-salario').value,
    disponibilidad: document.getElementById('pf-disp').value,
    movilidad: document.getElementById('pf-mov').value,
    headline: document.getElementById('pf-headline').value,
    summary: document.getElementById('pf-summary').value,
  };
  try {
    await api('/api/profiles/' + id, { method: 'PATCH', body: JSON.stringify(body) });
    document.getElementById('pf-status').innerHTML = '<p style="color:var(--ok)">✔ Guardado.</p>';
    await loadProfiles();
  } catch (e) {
    document.getElementById('pf-status').innerHTML = `<p style="color:var(--bad)">Error: ${esc(e.message)}</p>`;
  }
}

/* ---------------- Puestos objetivo ---------------- */
async function loadPuestos(pid) {
  if (!pid) return;
  puestosCache = await api(`/api/profiles/${pid}/puestos`);
  activePuestoId = (puestosCache.find((p) => p.activo) || puestosCache[0] || {}).id || null;
  const sel = document.getElementById('role-select');
  sel.innerHTML = puestosCache.map((p) =>
    `<option value="${p.id}" ${p.id === activePuestoId ? 'selected' : ''}>${esc(p.titulo)}${p.activo ? ' ★' : ''}</option>`).join('')
    || '<option value="">— sin puestos definidos —</option>';
  const act = puestosCache.find((p) => p.id === activePuestoId);
  if (act) {
    document.getElementById('pt-seniority').value = act.seniority;
    document.getElementById('pt-modality').value = act.modality || 'Presencial o hibrido';
    document.getElementById('pt-salario').innerHTML = salaryOptions(act.rango_salarial);
    document.getElementById('pt-info').innerHTML =
      `Puesto objetivo activo: <b>${esc(act.titulo)}</b> · ${esc(act.seniority)} · ${esc(act.modality)} · ` +
      `salario <b>${esc(act.rango_salarial || 'por definir')}</b> — el análisis usa esta meta.`;
  }
}

async function createPuesto() {
  const titulo = document.getElementById('pt-titulo').value.trim();
  if (!titulo) { alert('Escribe el título del puesto objetivo.'); return; }
  const body = {
    titulo,
    seniority: document.getElementById('pt-seniority').value,
    modality: document.getElementById('pt-modality').value,
    ubicacion: '',
    rango_salarial: document.getElementById('pt-salario').value,
    must_haves: document.getElementById('pt-must').value.split(',').map((s) => s.trim()).filter(Boolean),
    nice_to_haves: document.getElementById('pt-nice').value.split(',').map((s) => s.trim()).filter(Boolean),
  };
  await api(`/api/profiles/${activeId}/puestos`, { method: 'POST', body: JSON.stringify(body) });
  document.getElementById('pt-titulo').value = '';
  await loadPuestos(activeId);
}

/* ---------------- Dashboard + conexiones ---------------- */
async function loadDashboard() {
  try {
    const [o, p] = await Promise.all([
      api('/api/overview' + (activeId ? '?profile_id=' + activeId : '')),
      api('/api/profiles/' + activeId),
    ]);
    document.getElementById('profile-card').innerHTML = `
      <h2>${esc(p.nombre)}</h2>
      <p class="muted">${esc(p.email)} · ${esc(p.ubicacion)}</p>
      <p>Puesto objetivo: <b>${esc(o.puesto_objetivo?.titulo || '—')}</b> ·
        ${esc(o.puesto_objetivo?.seniority || '')} ·
        salario <b>${esc(o.puesto_objetivo?.rango_salarial || 'por definir')}</b></p>
      <p class="muted">Fuente: ${esc(p.fuente_cv)} · ${p.verificado ? 'verificado' : 'CV parseado'}</p>`;
    const score = o.score_global ?? '—';
    document.getElementById('kpi-row').innerHTML = `
      <div class="kpi"><b>${score}</b><small>Score XYZ/100</small></div>
      <div class="kpi"><b>${o.postulaciones}</b><small>Postulaciones</small></div>
      <div class="kpi"><b>${o.correos_pendientes}</b><small>Correos pendientes</small></div>
      <div class="kpi"><b>${esc((o.puesto_analizado || '—').split(' ')[0])}</b><small>Últ. análisis</small></div>`;
    document.getElementById('adapters').innerHTML = (o.adapters || []).map((a) => `
      <div class="gap-item">
        <b>${esc(a.plataforma)}</b> ·
        <span class="badge ${a.modo === 'autofill' ? 'ok' : 'warn'}">${esc(a.modo.toUpperCase())}</span>
        <div class="muted">${esc(a.descripcion)}</div>
        <div class="muted">${esc(a.tos_note)}</div>
      </div>`).join('');
    loadConnections();
  } catch (e) { console.error(e); }
}

async function loadConnections() {
  const conns = await api('/api/platforms/connections');
  document.getElementById('connections').innerHTML = (conns || []).map((c) => `
    <label class="conn">
      <input type="checkbox" ${c.conectada ? 'checked' : ''} onchange="toggleConnection('${c.plataforma}', this.checked)">
      <b>${esc(c.plataforma)}</b> <small class="muted">${esc(c.nota)}</small>
    </label>`).join('');
}

async function toggleConnection(plataforma, conectada) {
  await api('/api/platforms/connections', { method: 'PUT', body: JSON.stringify({ plataforma, conectada }) });
}

/* ---------------- Analisis ---------------- */
async function runAnalysis() {
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Analizando…';
  try {
    const selectedId = Number(document.getElementById('role-select').value);
    if (selectedId && selectedId !== activePuestoId) {
      await api(`/api/profiles/${activeId}/puestos/activo`, { method: 'POST', body: JSON.stringify({ puesto_id: selectedId }) });
      activePuestoId = selectedId;
      await loadPuestos(activeId);
    }
    const r = await api('/api/analyze', { method: 'POST', body: JSON.stringify({ profile_id: activeId, usar_puesto: true }) });
    const bars = r.components.map((c) => `
      <div class="gap-item">
        <b>${esc(c.name)}</b> (${c.peso}) — <b>${c.score}/100</b>
        <div class="bar"><span style="width:${c.score}%"></span></div>
      </div>`).join('');
    document.getElementById('analysis-result').innerHTML = `
      <div class="card">
        <h2>Resultado: ${esc(r.target_role)}</h2>
        <div class="kpi-row">
          <div class="kpi"><b>${r.score_global}</b><small>Score global /100</small></div>
          <div class="kpi"><b>${r.gaps.length}</b><small>Brechas</small></div>
        </div>
        ${bars}
        <p class="muted">${esc(r.resumen)}</p>
      </div>
      <div class="card"><h2>Brechas priorizadas</h2>
        ${(r.gaps || []).map((g) => `<div class="gap-item">
           <span class="badge ${g.prioridad === 'Alta' ? 'bad' : 'warn'}">${esc(g.prioridad)}</span>
           <b>${esc(g.titulo)}</b><div class="muted">${esc(g.detalle)}</div>
           <div>→ ${esc(g.sugerencia)}</div></div>`).join('') || '<p class="muted">Sin brechas críticas.</p>'}
      </div>
      <div class="card"><h2>Reescrituras sugeridas (formato XYZ)</h2>
        ${(r.reescrituras || []).slice(0, 8).map((w) => `<pre>${esc(w.original)}\n→ ${esc(w.guia)}</pre>`).join('') || '<p class="muted">Todos los logros están bien estructurados.</p>'}
      </div>
      <div class="card"><h2>Keywords a verificar antes de agregar (honestidad)</h2>
        ${(r.keywords_para_verificar || []).map((k) => `<span class="badge warn">${esc(k.keyword)} ✓ solo si lo dominas</span> `).join('') || '<p class="muted">Todas las keywords están cubiertas.</p>'}
      </div>`;
  } catch (e) {
    document.getElementById('analysis-result').innerHTML = `<div class="card" style="color:var(--bad)">Error: ${esc(e.message)}</div>`;
  } finally { btn.disabled = false; btn.textContent = 'Analizar CV'; }
}

/* ---------------- CV generado ---------------- */
async function generateCV(id) {
  const box = document.getElementById('cv-result');
  box.innerHTML = '<div class="card"><p>Generando CV corregido…</p></div>';
  try {
    const r = await api('/api/cv/generate', { method: 'POST', body: JSON.stringify({ profile_id: id }) });
    const cambios = (r.correcciones || []).map((c) => `
      <div class="gap-item">
        <div><span class="badge ok">corregido</span> <span class="muted">${esc(c.puesto)}</span></div>
        <div class="muted" style="text-decoration:line-through;opacity:.7">${esc(c.original)}</div>
        <div><b>${esc(c.mejorado)}</b></div>
      </div>`).join('');
    box.innerHTML = `
      <div class="card">
        <h2>✅ CV corregido generado — ${esc(r.candidato)}</h2>
        <p class="muted">${r.total_correcciones} correcciones (voz activa + estructura ATS). Las métricas faltantes <b>no se inventan</b>.</p>
        <a class="btn primary" href="${r.download_url}" download>⬇ DOCX</a>
        <a class="btn" href="${r.latex_url}" download>⬇ LaTeX (.tex)</a>
        <button class="btn" onclick="document.getElementById('cv-latex').classList.toggle('hidden')">Ver código LaTeX</button>
        <button class="btn" onclick="document.getElementById('cv-corrections').classList.toggle('hidden')">Ver correcciones aplicadas</button>
        <div id="cv-latex" class="hidden" style="margin-top:10px">
          <p class="muted">Pega el código en <a href="https://www.overleaf.com" target="_blank">Overleaf</a> o compílalo con <code>pdflatex</code>.</p>
          <pre style="max-height:260px;overflow:auto">${esc(r.latex || '')}</pre>
        </div>
        <div id="cv-corrections" class="hidden" style="margin-top:10px">${cambios || '<p class="muted">Sin correcciones pendientes.</p>'}</div>
      </div>
      <div class="card">
        <h2>Vista previa</h2>
        <iframe id="cv-frame" class="cv-frame" title="CV generado"></iframe>
        <p class="muted" style="margin-top:8px">💡 Ctrl+P → Guardar como PDF.</p>
      </div>`;
    document.getElementById('cv-frame').srcdoc = r.cv_html || '';
  } catch (e) {
    box.innerHTML = `<div class="card" style="color:var(--bad)">Error: ${esc(e.message)}</div>`;
  }
}

/* ---------------- Autofill (formularios) ---------------- */
async function loadBadges() {
  const adapters = await api('/api/adapters');
  document.getElementById('adapter-badges').innerHTML = adapters.map((a) => `
    <span class="badge ${a.modo === 'autofill' ? 'ok' : 'warn'}">${esc(a.plataforma)} · ${esc(a.modo)}</span>`).join('');
}

function renderFormUI(r) {
  formState = r;
  document.getElementById('form-result').innerHTML = `
    <div class="card">
      <h2>Formulario detectado (${esc(r.plataforma)}) — ${esc(r.vacante)} · Candidato: ${esc(r.candidato)}</h2>
      <p class="muted">${esc(r.regla_humana)}</p>
      ${(r.answers || []).map((a) => `
        <div class="answer-row">
          <label class="small">${esc(a.label)}</label>
          <textarea id="ans-${a.field_id}" ${a.necesita_input ? 'style="border-color:var(--warn)"' : ''}>${esc(a.answer)}</textarea>
        </div>`).join('')}
      <button class="btn primary" onclick="approveForm()">✔ Aprobar respuestas</button>
      <button class="btn" onclick="submitForm()" id="submit-btn" disabled>Enviar postulación (con aprobación)</button>
      <div id="form-status"></div>
    </div>`;
}

async function runFormPipeline() {
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Ejecutando pipeline…';
  try {
    const r = await api('/api/form/prepare', {
      method: 'POST',
      body: JSON.stringify({ profile_id: activeId, platform: 'test', vacante_titulo: 'Analista de Cobranzas', vacante_empresa: 'Empresa Ejemplo' }),
    });
    renderFormUI(r);
  } catch (e) {
    document.getElementById('form-result').innerHTML = `<div class="card" style="color:var(--bad)">Error: ${esc(e.message)}</div>`;
  } finally { btn.disabled = false; btn.textContent = '▶ Ejecutar pipeline (formulario de prueba)'; }
}

async function approveForm() {
  const edits = (formState.answers || []).map((a) => ({ field_id: a.field_id, answer: document.getElementById('ans-' + a.field_id).value }));
  await api(`/api/form/${formState.form_id}/approve`, { method: 'POST', body: JSON.stringify({ edits }) });
  document.getElementById('submit-btn').disabled = false;
  document.getElementById('form-status').innerHTML = `<p style="color:var(--ok)">✔ Aprobado. Ya puedes enviar.</p>`;
}

async function submitForm() {
  try {
    const r = await api(`/api/form/${formState.form_id}/submit`, { method: 'POST' });
    document.getElementById('form-status').innerHTML =
      `<p style="color:var(--ok)">✔ Postulación #${r.postulacion_id} registrada. Correo: <b>${esc(r.correo.estado)}</b> → ${esc(r.correo.destinatario)}</p>`;
    document.getElementById('submit-btn').disabled = true;
    loadApplications();
  } catch (e) {
    document.getElementById('form-status').innerHTML = `<p style="color:var(--bad)">${esc(e.message)}</p>`;
  }
}

/* ---------------- Empleos ---------------- */
async function searchJobs() {
  const status = document.getElementById('job-status');
  const box = document.getElementById('job-results');
  status.innerHTML = '<p>🔎 Buscando en Bumeran, Computrabajo, Indeed y LinkedIn (puede tardar ~40 seg)…</p>';
  box.innerHTML = '';
  try {
    const r = await api('/api/jobs/search', { method: 'POST', body: JSON.stringify({ profile_id: activeId }) });
    status.innerHTML = `<p style="color:var(--ok)">✔ Búsqueda para <b>${esc(r.candidato)}</b> — consulta: "${esc(r.query)}"</p>`;
    box.innerHTML = (r.plataformas || []).map((p) => `
      <div class="card">
        <h2>${esc(p.nombre)} <span class="badge ${p.estado === 'ok' ? 'ok' : 'warn'}">${esc(p.estado)}</span></h2>
        ${p.estado !== 'ok' ? `<p class="muted">${esc(p.nota)}</p>` : ''}
        <a class="btn" href="${esc(p.url)}" target="_blank" rel="noopener">Abrir búsqueda en ${esc(p.nombre)}</a>
        ${(p.resultados || []).map((j, i) => `
          <div class="gap-item" id="job-${esc(p.plataforma)}-${i}">
            <b>${esc(j.titulo)}</b> <span class="badge ok">${j.match}% match</span>
            <div class="muted">${esc(j.empresa)} · ${esc(j.ubicacion)}</div>
            <div>
              ${j.link ? `<a href="${esc(j.link)}" target="_blank" rel="noopener">Ver vacante ↗</a> · ` : ''}
              <button class="btn" onclick="postular(this)"
                data-plataforma="${esc(p.plataforma)}" data-titulo="${esc(j.titulo)}"
                data-empresa="${esc(j.empresa)}" data-url="${esc(j.link || '')}" data-idx="${i}">Postular</button>
              <span id="post-status-${esc(p.plataforma)}-${i}"></span>
            </div>
          </div>`).join('')}
      </div>`).join('');
  } catch (e) {
    status.innerHTML = `<p style="color:var(--bad)">Error: ${esc(e.message)}</p>`;
  }
}

async function postular(btn) {
  const { id } = btn.dataset;
  const status = document.getElementById(`post-status-${btn.dataset.plataforma}-${btn.dataset.idx}`);
  btn.disabled = true;
  try {
    const r = await api('/api/postulaciones', {
      method: 'POST',
      body: JSON.stringify({
        profile_id: activeId, plataforma: btn.dataset.plataforma,
        titulo: btn.dataset.titulo, empresa: btn.dataset.empresa, url: btn.dataset.url,
      }),
    });
    status.innerHTML = `<span class="badge ok">✔ Postulada #${r.postulacion_id} · correo: ${esc(r.correo.estado)} → ${esc(r.correo.destinatario)}</span>`;
    loadApplications();
  } catch (e) {
    status.innerHTML = `<span class="badge bad">Error: ${esc(e.message)}</span>`;
    btn.disabled = false;
  }
}

/* ---------------- Correo <-> solicitud ---------------- */
async function loadEmails() {
  const emails = await api('/api/emails');
  document.getElementById('email-list').innerHTML = `<div class="card"><table>
    <thead><tr><th>Remitente</th><th>Asunto</th><th>Clasificación</th><th>Formulario</th><th>Solicitud</th><th></th></tr></thead>
    <tbody>${(emails || []).map((e) => `
      <tr><td>${esc(e.remitente)}</td><td>${esc(e.asunto)}</td>
      <td><span class="badge ${e.clasificacion === 'requiere_accion' ? 'bad' : 'ok'}">${esc(e.clasificacion)}</span></td>
      <td>${e.tiene_formulario ? '📄 Sí' : '—'}</td>
      <td>${e.form_enviado ? '<span class="badge ok">postulado ✓</span>'
        : (e.form_id ? '<span class="badge warn">borrador #' + e.form_id + '</span>' : esc(e.estado))}</td>
      <td>${e.tiene_formulario && !e.form_enviado
        ? `<button class="btn" onclick="resolverEmail(${e.id})">Resolver con autofill</button>` : ''}</td>
      </tr>`).join('')}</tbody></table></div>`;
}

async function resolverEmail(emailId) {
  try {
    const r = await api(`/api/emails/${emailId}/resolver`, { method: 'POST' });
    renderFormUI(r);
    goTab('autofill');
    document.getElementById('form-status').innerHTML =
      `<p class="muted">📮 Formulario creado desde el correo #${emailId}. Revisa las respuestas, aprueba y envía.</p>`;
    loadEmails();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

/* ---------------- Postulaciones ---------------- */
async function loadApplications() {
  try {
    const apps = await api('/api/applications' + (activeId ? '?profile_id=' + activeId : ''));
    document.querySelector('#app-table tbody').innerHTML = (apps || []).map((a) => `
      <tr>
        <td><b>${esc(a.vacante?.titulo || '—')}</b><div class="muted">${esc(a.vacante?.empresa || '')}${a.vacante?.url ? ` · <a href="${esc(a.vacante.url)}" target="_blank">enlace ↗</a>` : ''}</div></td>
        <td>${esc(a.vacante?.plataforma || '—')}</td>
        <td><span class="badge ok">${esc(a.estado)}</span></td>
        <td>${esc((a.fecha || '').slice(0, 10))}</td>
        <td>${a.correo ? `<span class="badge ${a.correo.estado === 'enviado' ? 'ok' : 'warn'}">${esc(a.correo.estado)}</span> → ${esc(a.correo.destinatario)}` : '—'}</td>
        <td>${a.n_respuestas}</td>
      </tr>`).join('') || '<tr><td colspan="6" class="muted">Sin postulaciones. Crea una desde Empleos o desde el autofill.</td></tr>';
  } catch (e) { console.error(e); }
}

/* ---------------- Init ---------------- */
loadBadges().then(loadEmails);
loadProfiles().then(loadApplications);
