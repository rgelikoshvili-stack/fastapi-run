/* Bridge Hub — AI Learning & Patterns Management Module
   Enriches pg-learning with full pattern details, inline edit, delete, strength bars.
   Depends on: window.BASE, window.TOKEN, window.api, window.esc, window.toast
*/
(function () {
  const TIMEOUT_MS = 6000;

  async function _fetch(path, method = 'GET', body = null) {
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const opts = {
        method,
        headers: { Authorization: 'Bearer ' + window.TOKEN, 'Content-Type': 'application/json' },
        signal: ctrl.signal,
      };
      if (body !== null) opts.body = JSON.stringify(body);
      const r = await fetch(window.BASE + path, opts);
      clearTimeout(tid);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.json();
    } catch (e) {
      clearTimeout(tid);
      return { ok: false, _error: e.name === 'AbortError' ? 'timeout' : e.message };
    }
  }

  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  function _strengthBar(score, successCount, failureCount) {
    const pct = Math.round((score || 0) * 100);
    const color = pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--amber,#d97706)' : 'var(--red)';
    return `<div style="display:flex;align-items:center;gap:6px;font-size:11px;">
      <div style="flex:1;background:var(--gray-200);border-radius:4px;height:6px;overflow:hidden">
        <div style="height:100%;background:${color};width:${pct}%;transition:width .3s"></div>
      </div>
      <span style="color:${color};font-weight:700;min-width:30px">${pct}%</span>
      <span style="color:var(--green);font-size:10px">✓${successCount || 0}</span>
      <span style="color:var(--red);font-size:10px">✗${failureCount || 0}</span>
    </div>`;
  }

  function _buildPatternRow(p, isWeak = false) {
    const age = p.days_since_seen != null ? `${Math.round(p.days_since_seen)}d ago` : '—';
    const eligible = p.autopilot_eligible ? '🤖' : '';
    const statusColor = p.status === 'pattern_active' ? 'var(--green)' : p.status === 'archived' ? 'var(--gray-400)' : 'var(--amber,#d97706)';

    return `<div class="pl-row" id="pat-row-${p.id}" style="align-items:flex-start;flex-direction:column;gap:6px;padding:10px 0;border-bottom:1px solid var(--gray-100);">
      <div style="display:flex;align-items:center;justify-content:space-between;width:100%">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-family:var(--mono);font-weight:700;font-size:13px;color:var(--blue)">${esc(p.account_code || '—')}</span>
          <span style="font-size:11px;color:var(--gray-500)">${esc(p.pattern_type || '')}:</span>
          <span style="font-size:11px;font-weight:600">${esc(String(p.pattern_value || '').slice(0, 40))}</span>
          <span style="font-size:10px;color:${statusColor}">${esc(p.status || '')} ${eligible}</span>
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn btn-ghost btn-sm" style="font-size:10px" onclick="patternEdit(${p.id})">✏️ Edit</button>
          <button class="btn btn-ghost btn-sm" style="font-size:10px;color:var(--red)" onclick="patternDelete(${p.id})">🗑</button>
        </div>
      </div>
      ${_strengthBar(p.confidence_score, p.success_count, p.failure_count)}
      <div style="font-size:10px;color:var(--gray-400)">
        ${esc(p.reason || '—')} &nbsp;·&nbsp; ×${p.support_count || 0} seen &nbsp;·&nbsp; ${age}
        ${isWeak ? '<span style="color:var(--red);font-weight:600"> · WEAK</span>' : ''}
      </div>
    </div>`;
  }

  function _renderPatterns(topData) {
    const container = document.getElementById('patterns-full-body');
    if (!container) return;

    const top = topData.data?.top_patterns || [];
    const weak = topData.data?.weak_patterns || [];

    if (!top.length && !weak.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-text">Pattern-ები ვერ მოიძებნა. გააამტკიცე ან ასწორე Draft-ები სისტემა ისწავლის.</div></div>';
      return;
    }

    const weakIds = new Set(weak.map(w => w.id));

    container.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">
        <button class="btn btn-ghost btn-sm" onclick="window._patFilter='all';renderPatternFilter()">ყველა (${top.length})</button>
        <button class="btn btn-ghost btn-sm" onclick="window._patFilter='weak';renderPatternFilter()">სუსტი (${weak.length})</button>
        <button class="btn btn-ghost btn-sm" onclick="window._patFilter='auto';renderPatternFilter()">Auto-Pilot (${top.filter(p=>p.autopilot_eligible).length})</button>
      </div>
      <div id="pat-list">
        ${top.map(p => _buildPatternRow(p, weakIds.has(p.id))).join('')}
      </div>`;

    window._patData = { top, weak };
    window._patFilter = 'all';
  }

  window.renderPatternFilter = function () {
    const { top = [], weak = [] } = window._patData || {};
    const filter = window._patFilter || 'all';
    const weakIds = new Set(weak.map(w => w.id));
    let items;
    if (filter === 'weak') items = weak;
    else if (filter === 'auto') items = top.filter(p => p.autopilot_eligible);
    else items = top;

    const listEl = document.getElementById('pat-list');
    if (listEl) listEl.innerHTML = items.length
      ? items.map(p => _buildPatternRow(p, weakIds.has(p.id))).join('')
      : '<div class="empty-state"><div class="empty-text">ამ ფილტრისთვის Patterns არ მოიძებნა</div></div>';
  };

  window.patternEdit = async function (patId) {
    const row = document.getElementById('pat-row-' + patId);
    if (!row) return;
    const { top = [] } = window._patData || {};
    const p = top.find(x => x.id === patId);
    if (!p) return;

    row.querySelector('div:last-child')?.remove();
    const form = document.createElement('div');
    form.style.cssText = 'padding:10px;background:var(--blue-s);border-radius:8px;margin-top:8px;display:flex;flex-direction:column;gap:8px;';
    form.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
        <div>
          <label style="font-size:10px;color:var(--gray-500)">Account Code</label>
          <input id="pat-edit-acc-${patId}" class="finput" value="${esc(p.account_code || '')}" style="width:100%;margin-top:2px;font-family:var(--mono)">
        </div>
        <div>
          <label style="font-size:10px;color:var(--gray-500)">Status</label>
          <select id="pat-edit-st-${patId}" class="finput" style="width:100%;margin-top:2px">
            ${['pattern_active','pattern_candidate','archived'].map(s =>
              `<option value="${s}"${p.status===s?' selected':''}>${s}</option>`).join('')}
          </select>
        </div>
      </div>
      <div>
        <label style="font-size:10px;color:var(--gray-500)">Reason</label>
        <input id="pat-edit-reason-${patId}" class="finput" value="${esc(p.reason || '')}" style="width:100%;margin-top:2px">
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-blue btn-sm" onclick="patternSave(${patId})">💾 შენახვა</button>
        <button class="btn btn-ghost btn-sm" onclick="loadPatternsPanel()">✕ გაუქმება</button>
      </div>`;
    row.appendChild(form);
  };

  window.patternSave = async function (patId) {
    const acc = document.getElementById('pat-edit-acc-' + patId)?.value?.trim();
    const st  = document.getElementById('pat-edit-st-' + patId)?.value;
    const rsn = document.getElementById('pat-edit-reason-' + patId)?.value?.trim();
    if (!acc) { toast('Account Code ცარიელია', 'err'); return; }

    const d = await _fetch('/learning/patterns/' + patId, 'PATCH', { account_code: acc, status: st, reason: rsn });
    if (!d?.ok) { toast('შენახვა ვერ მოხდა: ' + (d?._error || d?.message || ''), 'err'); return; }
    toast('✅ Pattern განახლდა', 'ok');
    await loadPatternsPanel();
  };

  window.patternDelete = async function (patId) {
    if (!confirm('გსურს ამ Pattern-ის არქივირება?')) return;
    const d = await _fetch('/learning/patterns/' + patId, 'DELETE');
    if (!d?.ok) { toast('წაშლა ვერ მოხდა', 'err'); return; }
    toast('🗑 Pattern დაარქივდა', 'ok');
    await loadPatternsPanel();
  };

  async function loadPatternsPanel() {
    const container = document.getElementById('patterns-full-body');
    if (!container) return;
    container.innerHTML = '<div class="loading-row"><span class="spinner"></span></div>';
    const d = await _fetch('/learning/patterns/top');
    if (!d?.ok) {
      container.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div class="empty-text">Patterns ვერ ჩაიტვირთა</div></div>`;
      return;
    }
    _renderPatterns(d);
  }

  function _patchLearningPage() {
    const pg = document.getElementById('pg-learning');
    if (!pg || pg.dataset.lpPatched) return;
    pg.dataset.lpPatched = 'true';

    const patCard = pg.querySelector('.card:last-child');
    if (patCard) {
      const body = patCard.querySelector('.card-body');
      if (body) {
        body.id = 'patterns-full-body';
        const header = patCard.querySelector('.card-header');
        if (header) {
          const title = header.querySelector('.card-title');
          if (title) title.textContent = '🎯 Learned Patterns';
          const btn = document.createElement('button');
          btn.className = 'btn btn-ghost btn-sm';
          btn.textContent = '⟳';
          btn.onclick = loadPatternsPanel;
          header.appendChild(btn);
        }
      }
    }

    loadPatternsPanel();
  }

  const _orig = window.goPage;
  if (_orig) {
    window.goPage = function (page, el) {
      _orig(page, el);
      if (page === 'learning') requestAnimationFrame(_patchLearningPage);
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (window.curPage === 'learning') _patchLearningPage();
  });
})();
