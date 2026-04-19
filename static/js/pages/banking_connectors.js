/* Bridge Hub — Banking Connectors Module
   Patches pg-bank with real TBC/BOG status, Force Sync, graceful degradation.
   Depends on: window.BASE, window.TOKEN, window.toast, window.api
*/
(function () {
  const TIMEOUT_MS = 8000;

  async function _bankFetch(path, method = 'GET', body = null) {
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const opts = {
        method,
        headers: { Authorization: 'Bearer ' + window.TOKEN, 'Content-Type': 'application/json' },
        signal: ctrl.signal,
      };
      if (body) opts.body = JSON.stringify(body);
      const r = await fetch(window.BASE + path, opts);
      clearTimeout(tid);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.json();
    } catch (e) {
      clearTimeout(tid);
      if (e.name === 'AbortError') return { ok: false, _timeout: true };
      return { ok: false, _error: e.message };
    }
  }

  function _statusPill(s) {
    if (!s) return '<span class="status-pill sp-demo">UNKNOWN</span>';
    const st = String(s).toUpperCase();
    if (st === 'LIVE' || st === 'CONNECTED') return '<span class="status-pill" style="background:#dcfce7;color:#15803d">LIVE</span>';
    if (st === 'DEMO' || st === 'MOCK') return '<span class="status-pill sp-demo">DEMO</span>';
    if (st === 'ERROR' || st === 'TIMEOUT') return '<span class="status-pill" style="background:#fef2f2;color:#dc2626">ERROR</span>';
    return `<span class="status-pill sp-demo">${st}</span>`;
  }

  function _renderBankStatus(container, bankData) {
    const banks = bankData?.banks || {};
    const tbc = banks.tbc || {};
    const bog = banks.bog || {};

    const tbcStatus = tbc.status || (bankData?._timeout ? 'TIMEOUT' : 'DEMO');
    const bogStatus = bog.status || (bankData?._timeout ? 'TIMEOUT' : 'DEMO');

    const degraded = bankData?._timeout || bankData?._error;
    const warningHtml = degraded
      ? `<div style="padding:10px;background:var(--amber-s,#fffbeb);border-radius:8px;border:1px solid rgba(245,158,11,.2);font-size:12px;margin-bottom:10px">
           ⚠️ ბანკის API ${bankData._timeout ? 'დაგვიანება (timeout)' : 'შეცდომა: ' + (bankData._error || '')}.
           კავშირი Settings-ში კონფიგურირდება.
         </div>`
      : '';

    container.innerHTML = warningHtml + `
      <div class="recon-widget">
        <div class="recon-row">
          <div class="recon-left">
            <div class="recon-bank-icon">🏦</div>
            <div>
              <div class="recon-name">TBC Bank</div>
              <div class="recon-sub" id="tbc-sub-bc">${window.esc ? window.esc(tbc.last_sync || 'DEMO mode') : (tbc.last_sync || 'DEMO mode')}</div>
            </div>
          </div>
          <div class="recon-right" style="gap:8px;">
            <div class="recon-amount" id="tbc-cnt-bc">${tbc.transactions_today ?? '—'}</div>
            ${_statusPill(tbcStatus)}
            <button class="btn btn-ghost btn-sm" id="tbc-sync-btn" onclick="bankForceSync('tbc')">⟳ Sync</button>
          </div>
        </div>
        <div class="recon-row">
          <div class="recon-left">
            <div class="recon-bank-icon">🏦</div>
            <div>
              <div class="recon-name">Bank of Georgia</div>
              <div class="recon-sub" id="bog-sub-bc">${window.esc ? window.esc(bog.last_sync || 'DEMO mode') : (bog.last_sync || 'DEMO mode')}</div>
            </div>
          </div>
          <div class="recon-right" style="gap:8px;">
            <div class="recon-amount" id="bog-cnt-bc">${bog.transactions_today ?? '—'}</div>
            ${_statusPill(bogStatus)}
            <button class="btn btn-ghost btn-sm" id="bog-sync-btn" onclick="bankForceSync('bog')">⟳ Sync</button>
          </div>
        </div>
        <div class="recon-row" style="background:var(--blue-s);border-color:rgba(29,107,243,.15);">
          <div class="recon-left">
            <div class="recon-bank-icon">🌉</div>
            <div>
              <div class="recon-name">Balance.ge</div>
              <div class="recon-sub">ERP Connector · API Key ელოდება</div>
            </div>
          </div>
          <div class="recon-right" style="gap:8px;">
            <button class="btn btn-ghost btn-sm" onclick="goPage('settings',null)">⚙️ Setup</button>
            <span class="status-pill sp-demo">DEMO</span>
          </div>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;">
        <button class="btn btn-blue btn-sm" onclick="bankForceSync('all')">⚡ Force Sync All</button>
        <button class="btn btn-ghost btn-sm" onclick="loadBankStatus()">⟳ Refresh Status</button>
        <button class="btn btn-ghost btn-sm" onclick="goPage('settings',null)">⚙️ API Keys</button>
      </div>`;
  }

  window.loadBankStatus = async function () {
    const pg = document.getElementById('pg-bank');
    if (!pg) return;

    const wrap = document.getElementById('bank-status-bc');
    if (!wrap) return;
    wrap.innerHTML = '<div class="loading-row"><span class="spinner"></span> სტატუსი...</div>';

    const d = await _bankFetch('/bank-sync/status');
    _renderBankStatus(wrap, d);
  };

  window.bankForceSync = async function (bank) {
    const btnId = bank === 'tbc' ? 'tbc-sync-btn' : bank === 'bog' ? 'bog-sync-btn' : null;
    const btn = btnId ? document.getElementById(btnId) : null;
    if (btn) { btn.disabled = true; btn.textContent = '⏳'; }

    toast(`🔄 ${bank === 'all' ? 'ყველა ბანკი' : bank.toUpperCase()} sync მიმდინარეობს...`, 'info');

    let path, body;
    if (bank === 'tbc') { path = '/bank-sync/tbc/sync'; body = { days: 7 }; }
    else if (bank === 'bog') { path = '/bank-sync/bog/sync'; body = { days: 7 }; }
    else { path = '/bank-sync/sync-all'; body = { days: 7 }; }

    const d = await _bankFetch(path, 'POST', body);

    if (btn) { btn.disabled = false; btn.textContent = '⟳ Sync'; }

    if (d?._timeout) {
      toast('⚠️ Bank API timeout — შეამოწმე API Keys Settings-ში', 'warn');
      return;
    }
    if (!d || d._error || !d.ok) {
      toast(`❌ Sync შეცდომა: ${d?._error || d?.message || 'API N/A'}`, 'err');
      return;
    }

    const cnt = d.data?.imported || d.imported || d.data?.created || 0;
    toast(`✅ ${bank.toUpperCase()} sync: ${cnt} ტრანზაქცია`, 'ok');
    setTimeout(window.loadBankStatus, 500);
  };

  function _patchBankPage() {
    const pg = document.getElementById('pg-bank');
    if (!pg || pg.dataset.bcPatched) return;
    pg.dataset.bcPatched = 'true';

    let wrap = document.getElementById('bank-status-bc');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.id = 'bank-status-bc';
      wrap.style.cssText = 'margin-top:14px';
      const firstCard = pg.querySelector('.card');
      if (firstCard) {
        const body = firstCard.querySelector('.card-body,.recon-widget') || firstCard;
        body.parentNode.insertBefore(wrap, body.nextSibling);
      } else {
        pg.prepend(wrap);
      }
    }
    window.loadBankStatus();
  }

  const _orig = window.goPage;
  if (_orig) {
    window.goPage = function (page, el) {
      _orig(page, el);
      if (page === 'bank') requestAnimationFrame(_patchBankPage);
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (window.curPage === 'bank') _patchBankPage();
  });
})();
