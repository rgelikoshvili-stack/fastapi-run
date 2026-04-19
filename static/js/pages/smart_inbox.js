/* Bridge Hub — Smart Inbox & Hybrid Matcher Module
   Patches pg-inbox with real email invoice list + multi-line split suggestions.
   Hybrid Matcher: if invoice total > RS.ge zednadebi → propose split journal entry.
   Depends on: window.BASE, window.TOKEN, window.toast, window.api, window.esc
*/
(function () {
  const TIMEOUT_MS = 8000;
  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');

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

  function _fmtGEL(v) {
    return Number(v || 0).toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₾';
  }

  function _hybridMatchWarning(invoice) {
    const invAmt  = parseFloat(invoice.amount || invoice.total_amount || 0);
    const rsAmt   = parseFloat(invoice.rs_ge_amount || invoice.zednadebi_amount || 0);
    if (!invAmt || !rsAmt || Math.abs(invAmt - rsAmt) < 0.01) return null;
    const diff = invAmt - rsAmt;
    return {
      invoice_amount: invAmt,
      rs_amount: rsAmt,
      diff: diff,
      message: diff > 0
        ? `ფაქტურა (${_fmtGEL(invAmt)}) > ზედნადები (${_fmtGEL(rsAmt)}) — სავარაუდოდ საქ.+მომს. (${_fmtGEL(diff)} — სხვა მუხლი)`
        : `ზედნადები (${_fmtGEL(rsAmt)}) > ფაქტურა (${_fmtGEL(invAmt)}) — ვათვალიერებ...`,
      needs_split: diff > 0,
    };
  }

  function _buildInvoiceCard(item) {
    const hybrid = _hybridMatchWarning(item);
    const statusColor = item.status === 'processed' ? 'var(--green)' : item.status === 'error' ? 'var(--red)' : 'var(--amber,#d97706)';

    return `<div class="card" style="margin-bottom:12px;" id="inbox-item-${esc(item.id || item.message_id || '')}">
      <div class="card-header">
        <div>
          <div class="card-title" style="font-size:13px;">${esc(item.subject || item.filename || 'Invoice')}</div>
          <div style="font-size:11px;color:var(--gray-400)">${esc(item.sender || item.from || '')} · ${esc(item.received_at || item.date || '')}</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:13px;font-weight:700;color:var(--blue)">${_fmtGEL(item.amount || item.total_amount)}</span>
          <span style="font-size:10px;padding:2px 8px;border-radius:20px;background:var(--gray-100);color:${statusColor}">${esc(item.status || 'pending')}</span>
        </div>
      </div>
      ${hybrid ? `
      <div style="margin:0 16px 12px;padding:10px;background:var(--amber-s,#fffbeb);border:1px solid rgba(245,158,11,.2);border-radius:8px;font-size:12px;">
        <div style="font-weight:600;color:var(--amber,#d97706);margin-bottom:4px">🔀 Hybrid Matcher</div>
        <div>${esc(hybrid.message)}</div>
        ${hybrid.needs_split ? `
        <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn btn-amber btn-sm" style="background:var(--amber-s,#fffbeb);color:var(--amber,#d97706);border:1px solid rgba(245,158,11,.3);"
            onclick="inboxSplitDraft(${JSON.stringify(item).replace(/"/g,'&quot;')})">
            ✂️ გაყოფა (საქ. + მომს.)
          </button>
          <button class="btn btn-ghost btn-sm" onclick="inboxProcessSingle(${JSON.stringify(item.id||item.message_id||'').replace(/"/g,'&quot;')})">
            📝 ერთი Draft
          </button>
        </div>` : ''}
      </div>` : ''}
      <div class="card-body" style="padding-top:0;display:flex;gap:8px;flex-wrap:wrap;">
        ${item.status !== 'processed' ? `
          <button class="btn btn-blue btn-sm" onclick="inboxProcessSingle('${esc(String(item.id||item.message_id||''))}')">📝 Draft შექმნა</button>
          <button class="btn btn-ghost btn-sm" onclick="inboxPreview('${esc(String(item.id||item.message_id||''))}','${esc(item.filename||'')}')">👁 Preview</button>
        ` : '<span style="color:var(--green);font-size:12px">✅ დამუშავებულია</span>'}
        <button class="btn btn-ghost btn-sm" style="color:var(--red)" onclick="inboxDismiss('${esc(String(item.id||item.message_id||''))}')">✕</button>
      </div>
    </div>`;
  }

  async function _loadInbox() {
    const body = document.getElementById('inbox-smart-body');
    if (!body) return;
    body.innerHTML = '<div class="loading-row"><span class="spinner"></span> Inbox იტვირთება...</div>';

    const d = await _fetch('/email-invoice/inbox');

    if (d?._error || !d?.ok) {
      const isDemo = d?._error === 'timeout' || d?._error?.includes('404') || !d;
      body.innerHTML = `
        <div style="padding:16px;background:var(--amber-s,#fffbeb);border-radius:10px;border:1px solid rgba(245,158,11,.2);font-size:12px;">
          ${isDemo
            ? '📧 Email Inbox API ელოდება კავშირს. Settings-ში კონფიგურირება საჭიროა IMAP/SMTP.'
            : `❌ Inbox შეცდომა: ${esc(d?._error || d?.message || '')}`}
          <br><br>
          <button class="btn btn-ghost btn-sm" onclick="goPage('settings',null)">⚙️ Email Setup</button>
          <button class="btn btn-ghost btn-sm" onclick="loadSmartInbox()" style="margin-left:8px">⟳ Retry</button>
        </div>`;
      return;
    }

    const items = d.data?.messages || d.data?.items || d.items || d.messages || [];
    if (!items.length) {
      body.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><div class="empty-text">ახალი ინვოისი არ არის</div></div>';
      return;
    }

    const badge = document.getElementById('sb-inbox');
    if (badge) badge.textContent = items.length;

    body.innerHTML = items.map(it => _buildInvoiceCard(it)).join('');
  }

  window.loadSmartInbox = _loadInbox;

  window.inboxProcessSingle = async function (messageId) {
    if (!messageId) return;
    toast('📝 Draft იქმნება...', 'info');
    const d = await _fetch('/email-invoice/confirm-process', 'POST', { message_id: messageId });
    if (d?.ok) {
      toast('✅ Draft შეიქმნა', 'ok');
      _loadInbox();
    } else {
      toast('Draft შეცდომა: ' + (d?.message || d?._error || ''), 'err');
    }
  };

  window.inboxPreview = async function (messageId, filename) {
    if (!messageId || !filename) { toast('Preview: ID ან ფაილი ვერ მოიძებნა', 'warn'); return; }
    window.open(window.BASE + '/email-invoice/preview/' + encodeURIComponent(messageId) + '/' + encodeURIComponent(filename), '_blank');
  };

  window.inboxDismiss = function (itemId) {
    const el = document.getElementById('inbox-item-' + itemId);
    if (el) el.style.display = 'none';
  };

  window.inboxSplitDraft = async function (item) {
    if (typeof item === 'string') { try { item = JSON.parse(item); } catch(_) { return; } }

    const invAmt = parseFloat(item.amount || item.total_amount || 0);
    const rsAmt  = parseFloat(item.rs_ge_amount || item.zednadebi_amount || 0);
    const diff   = invAmt - rsAmt;

    toast('✂️ გაყოფილი Draft-ები იქმნება...', 'info');

    const [d1, d2] = await Promise.all([
      _fetch('/api/ai/classify', 'POST', {
        description: (item.subject || item.filename || 'Invoice') + ' — საქონელი',
        amount: rsAmt,
        source: 'inbox_split',
      }),
      _fetch('/api/ai/classify', 'POST', {
        description: (item.subject || item.filename || 'Invoice') + ' — მომსახურება',
        amount: diff,
        source: 'inbox_split',
      }),
    ]);

    const ok1 = d1?.ok || d1?.data?.ok;
    const ok2 = d2?.ok || d2?.data?.ok;

    if (ok1 && ok2) {
      toast(`✅ 2 Draft შეიქმნა: ${_fmtGEL(rsAmt)} (საქ.) + ${_fmtGEL(diff)} (მომს.)`, 'ok');
      _loadInbox();
    } else {
      toast('Split draft-ები ვერ შეიქმნა — სცადე ხელით', 'warn');
    }
  };

  function _patchInboxPage() {
    const pg = document.getElementById('pg-inbox');
    if (!pg || pg.dataset.siPatched) return;
    pg.dataset.siPatched = 'true';

    const existCard = pg.querySelector('.card');
    if (existCard) {
      const header = existCard.querySelector('.card-header');
      if (header) {
        const btn = document.createElement('button');
        btn.className = 'btn btn-ghost btn-sm';
        btn.textContent = '⟳';
        btn.onclick = _loadInbox;
        header.appendChild(btn);
      }
      let body = existCard.querySelector('.card-body');
      if (!body) {
        body = document.createElement('div');
        body.className = 'card-body';
        existCard.appendChild(body);
      }
      body.id = 'inbox-smart-body';
    } else {
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `<div class="card-header"><div class="card-title">📧 Smart Inbox</div><button class="btn btn-ghost btn-sm" onclick="loadSmartInbox()">⟳</button></div><div class="card-body" id="inbox-smart-body"></div>`;
      pg.prepend(card);
    }

    _loadInbox();
  }

  const _orig = window.goPage;
  if (_orig) {
    window.goPage = function (page, el) {
      _orig(page, el);
      if (page === 'inbox') requestAnimationFrame(_patchInboxPage);
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (window.curPage === 'inbox') _patchInboxPage();
  });
})();
