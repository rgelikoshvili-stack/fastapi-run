/* Bridge Hub — Shadow Posting (Pre-Approve Preview) Module
   Intercepts approve() calls, shows Dr/Cr impact modal, then proceeds.
   Depends on: window.BASE, window.TOKEN, window.toast, window.approve (existing)
*/
(function () {
  const TIMEOUT_MS = 5000;

  async function _getPreview(draftId) {
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const r = await fetch(window.BASE + '/posting/preview/' + draftId, {
        headers: { Authorization: 'Bearer ' + window.TOKEN },
        signal: ctrl.signal,
      });
      clearTimeout(tid);
      if (!r.ok) return null;
      return await r.json();
    } catch (_) {
      clearTimeout(tid);
      return null;
    }
  }

  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  function _fmtGEL(v) {
    return Number(v || 0).toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₾';
  }

  function _showPreviewModal(draftId, previewData, onConfirm) {
    document.getElementById('shadow-modal')?.remove();

    const p = previewData?.preview ? previewData : null;
    const draft = p?.draft || {};
    const impact = p?.impact || {};

    const plColor = (impact.pl_impact || 0) >= 0 ? 'var(--green)' : 'var(--red)';
    const plSign  = (impact.pl_impact || 0) >= 0 ? '+' : '';

    const modal = document.createElement('div');
    modal.id = 'shadow-modal';
    modal.style.cssText = `
      position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;
      background:rgba(0,0,0,.45);padding:16px;`;

    modal.innerHTML = `
      <div style="background:#fff;border-radius:16px;max-width:480px;width:100%;padding:24px;box-shadow:0 20px 60px rgba(0,0,0,.25);max-height:90vh;overflow-y:auto;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
          <div style="font-size:16px;font-weight:700;">📋 Posting Preview #${draftId}</div>
          <button onclick="document.getElementById('shadow-modal').remove()" style="background:none;border:none;font-size:20px;cursor:pointer;color:var(--gray-400)">✕</button>
        </div>

        ${!p ? '<div style="padding:16px;text-align:center;color:var(--gray-500)">Preview ვერ ჩაიტვირთა — ამ ნაბიჯის გამოტოვება შესაძლებელია.</div>' : `
        <!-- Draft summary -->
        <div style="background:var(--gray-50);border-radius:10px;padding:12px;margin-bottom:14px;font-size:12px;line-height:1.7;">
          <div><b>აღწერა:</b> ${esc(draft.description)}</div>
          <div><b>თანხა:</b> <span style="font-weight:700;color:var(--blue)">${_fmtGEL(draft.amount)}</span></div>
          <div><b>Confidence:</b> ${Math.round((draft.confidence || 0) * 100)}%</div>
        </div>

        <!-- Dr / Cr accounts -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px;">
          <div style="padding:10px;background:#e0f2fe;border-radius:10px;text-align:center;">
            <div style="font-size:10px;color:#0369a1;font-weight:600;margin-bottom:4px">DEBIT (Dr)</div>
            <div style="font-family:var(--mono);font-size:18px;font-weight:700;color:#0369a1">${esc(draft.debit_account || impact.debit_category?.toUpperCase() || '—')}</div>
            <div style="font-size:10px;color:#0369a1;margin-top:2px">${esc(impact.debit_category || '')}</div>
          </div>
          <div style="padding:10px;background:#dcfce7;border-radius:10px;text-align:center;">
            <div style="font-size:10px;color:#15803d;font-weight:600;margin-bottom:4px">CREDIT (Cr)</div>
            <div style="font-family:var(--mono);font-size:18px;font-weight:700;color:#15803d">${esc(draft.credit_account || '—')}</div>
            <div style="font-size:10px;color:#15803d;margin-top:2px">${esc(impact.credit_category || '')}</div>
          </div>
        </div>

        <!-- P&L impact -->
        ${impact.pl_impact != null ? `
        <div style="padding:10px;border-radius:10px;background:${(impact.pl_impact||0)>=0?'#f0fdf4':'#fef2f2'};margin-bottom:12px;font-size:12px;">
          <b>P&L გავლენა:</b>
          <span style="color:${plColor};font-weight:700;margin-left:6px">${plSign}${_fmtGEL(impact.pl_impact)}</span>
          <span style="color:var(--gray-500);margin-left:6px">(${impact.pl_direction || ''})</span>
        </div>` : ''}

        <!-- Notes -->
        ${(impact.notes||[]).length ? `
        <div style="font-size:11px;color:var(--gray-600);padding:10px;background:var(--gray-50);border-radius:8px;margin-bottom:14px;">
          ${(impact.notes||[]).map(n => `<div>• ${esc(n)}</div>`).join('')}
        </div>` : ''}
        `}

        <!-- Action buttons -->
        <div style="display:flex;gap:10px;justify-content:flex-end;">
          <button class="btn btn-ghost btn-sm" onclick="document.getElementById('shadow-modal').remove()">გაუქმება</button>
          <button class="btn btn-green btn-sm" id="shadow-confirm-btn" onclick="shadowConfirm(${draftId})">
            ✅ დადასტურება
          </button>
        </div>
      </div>`;

    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });

    window._shadowOnConfirm = onConfirm;
  }

  window.shadowConfirm = function (draftId) {
    document.getElementById('shadow-modal')?.remove();
    if (typeof window._shadowOnConfirm === 'function') {
      window._shadowOnConfirm(draftId);
      window._shadowOnConfirm = null;
    }
  };

  window.approveWithPreview = async function (draftId, onConfirm) {
    const preview = await _getPreview(draftId);
    _showPreviewModal(draftId, preview, onConfirm);
  };
})();
