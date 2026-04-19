/* Bridge Hub — Dashboard KPI Enrichment Module
   Enhances pg-dashboard with insights: 6-month trends, runway warning, anomaly badge.
   Depends on: window.BASE, window.TOKEN, window.api, window.esc, window.toast
*/
(function () {
  const TIMEOUT_MS = 6000;

  async function _apiFetch(path) {
    try {
      const ctrl = new AbortController();
      const tid = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
      const r = await fetch(window.BASE + path, {
        headers: { Authorization: 'Bearer ' + window.TOKEN },
        signal: ctrl.signal,
      });
      clearTimeout(tid);
      if (!r.ok) return null;
      return await r.json();
    } catch (_) {
      return null;
    }
  }

  function _fmt(v, dec = 0) {
    return Number(v || 0).toLocaleString('en', {
      minimumFractionDigits: dec,
      maximumFractionDigits: dec,
    });
  }

  function _sparkline(trends) {
    if (!trends || !trends.length) return '';
    const maxV = Math.max(...trends.map(t => Math.max(t.revenue || 0, t.expenses || 0)), 1);
    const bars = trends.slice(-6).map(t => {
      const rh = Math.round(((t.revenue || 0) / maxV) * 44);
      const eh = Math.round(((t.expenses || 0) / maxV) * 44);
      const label = (t.month || '').slice(5);
      return `<div style="display:flex;flex-direction:column;align-items:center;gap:2px;flex:1;">
        <div style="display:flex;gap:2px;align-items:flex-end;height:46px;">
          <div style="width:6px;background:var(--green);border-radius:2px 2px 0 0;height:${rh}px" title="Revenue ${_fmt(t.revenue)} ₾"></div>
          <div style="width:6px;background:var(--red);border-radius:2px 2px 0 0;height:${eh}px" title="Expenses ${_fmt(t.expenses)} ₾"></div>
        </div>
        <div style="font-size:9px;color:var(--gray-400)">${label}</div>
      </div>`;
    }).join('');
    return `<div style="display:flex;gap:4px;align-items:flex-end;padding:8px 0 4px;">${bars}</div>
      <div style="display:flex;gap:10px;font-size:10px;color:var(--gray-500)">
        <span><span style="display:inline-block;width:8px;height:8px;background:var(--green);border-radius:2px;margin-right:3px"></span>Revenue</span>
        <span><span style="display:inline-block;width:8px;height:8px;background:var(--red);border-radius:2px;margin-right:3px"></span>Expenses</span>
      </div>`;
  }

  function _injectTrendsCard(d) {
    const pg = document.getElementById('pg-dashboard');
    if (!pg || pg.dataset.kpiEnriched) return;
    pg.dataset.kpiEnriched = 'true';

    const rev = d.revenue_vs_expenses || {};
    const runway = d.runway || {};
    const anomalyCount = (d.anomalies || []).length;
    const dupeCount = (d.possible_duplicates || []).length;

    const runwayHtml = runway.runway_days != null
      ? `<div style="padding:8px;border-radius:8px;background:${runway.warning ? 'var(--red-s,#fef2f2)' : 'var(--green-s)'};border:1px solid ${runway.warning ? 'rgba(220,38,38,.2)' : 'rgba(34,197,94,.2)'};font-size:12px;margin-top:8px">
           ${runway.warning ? '⚠️' : '✅'} Cash Runway: <b>${runway.runway_days} დღე</b>
           &nbsp;·&nbsp; Daily burn: ${_fmt(runway.daily_burn_gel, 0)} ₾
         </div>`
      : '';

    const alertsHtml = (anomalyCount > 0 || dupeCount > 0)
      ? `<div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;">
           ${anomalyCount > 0 ? `<span style="padding:4px 10px;background:var(--amber-s,#fffbeb);border-radius:20px;font-size:11px;color:var(--amber,#d97706);font-weight:600">⚠️ ${anomalyCount} მაღ. ანომალია</span>` : ''}
           ${dupeCount > 0 ? `<span style="padding:4px 10px;background:var(--red-s,#fef2f2);border-radius:20px;font-size:11px;color:var(--red);font-weight:600">🔁 ${dupeCount} შეს. დუბლიკატი</span>` : ''}
         </div>`
      : '';

    const card = document.createElement('div');
    card.className = 'card';
    card.id = 'dash-insights-card';
    card.style.cssText = 'margin-top:16px;grid-column:1/-1';
    card.innerHTML = `
      <div class="card-header">
        <div class="card-title">📈 P&L Trends · 6 თვე</div>
        <div style="display:flex;gap:8px;align-items:center;">
          <span style="font-size:12px;color:${rev.profitable ? 'var(--green)' : 'var(--red)'};font-weight:700">
            Net: ${rev.profitable ? '+' : ''}${_fmt(rev.net, 0)} ₾
          </span>
          <button class="btn btn-ghost btn-sm" onclick="enrichDashboard(true)">⟳</button>
        </div>
      </div>
      <div class="card-body">
        ${_sparkline(d.trends)}
        ${runwayHtml}
        ${alertsHtml}
      </div>`;

    const rowMain = pg.querySelector('.row-main') || pg.querySelector('.row-2');
    if (rowMain && rowMain.parentNode) {
      rowMain.parentNode.insertBefore(card, rowMain.nextSibling);
    } else {
      pg.appendChild(card);
    }
  }

  window.enrichDashboard = async function (force = false) {
    if (!window.TOKEN) return;
    const pg = document.getElementById('pg-dashboard');
    if (!pg) return;
    if (!force && pg.dataset.kpiEnriched) return;
    pg.dataset.kpiEnriched = '';

    const existingCard = document.getElementById('dash-insights-card');
    if (existingCard) existingCard.remove();

    const d = await _apiFetch('/dashboard/insights');
    if (!d || !d.ok) return;

    _injectTrendsCard(d);
  };

  const _orig = window.goPage;
  if (_orig) {
    window.goPage = function (page, el) {
      _orig(page, el);
      if (page === 'dashboard') requestAnimationFrame(() => enrichDashboard(false));
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (window.curPage === 'dashboard' || !window.curPage) enrichDashboard(false);
  });
})();
