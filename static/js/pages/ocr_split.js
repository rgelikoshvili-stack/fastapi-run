/* Bridge Hub — OCR Split-View Module
   Replaces the basic OCR result card with a two-panel view:
   Left: PDF/image preview  |  Right: AI-extracted line items
   Depends on: window.BASE, window.TOKEN, window.TENANT, window.toast, window.api, window.esc
*/

(function() {
  // Patch the OCR page to split-view after DOM ready
  function _patchOCRPage() {
    const page = document.getElementById('pg-ocr');
    if (!page || page.dataset.splitPatched) return;
    page.dataset.splitPatched = 'true';

    page.innerHTML = `
      <div class="row-2" style="align-items:flex-start;">
        <!-- LEFT: upload + preview -->
        <div style="display:flex;flex-direction:column;gap:14px;">
          <div class="card">
            <div class="card-header">
              <div class="card-title">🧾 Invoice OCR</div>
              <button class="btn btn-blue btn-sm" onclick="document.getElementById('ocr-file-split').click()">📁 ფაილი</button>
              <input type="file" id="ocr-file-split" style="display:none"
                accept=".pdf,.xlsx,.xls,.png,.jpg,.jpeg" onchange="ocrSplitRun(this)"/>
            </div>
            <div class="card-body" id="ocr-drop-zone"
              ondragover="event.preventDefault();this.classList.add('uz-drag')"
              ondragleave="this.classList.remove('uz-drag')"
              ondrop="ocrSplitDrop(event)">
              <div class="upload-zone" id="ocr-upload-zone" onclick="document.getElementById('ocr-file-split').click()">
                <div class="uz-icon">📁</div>
                <div class="uz-title">ჩამოაგდე ან დააჭირე</div>
                <div class="uz-sub">PDF · XLSX · PNG · JPG — მაქს. 10MB</div>
              </div>
            </div>
          </div>
          <!-- PDF/Image preview -->
          <div class="card" id="ocr-preview-card" style="display:none">
            <div class="card-header">
              <div class="card-title" id="ocr-preview-filename">Preview</div>
            </div>
            <div class="card-body" style="padding:0;overflow:hidden;border-radius:0 0 12px 12px">
              <iframe id="ocr-pdf-frame" style="width:100%;height:520px;border:none;display:none"></iframe>
              <img id="ocr-img-preview" style="width:100%;max-height:520px;object-fit:contain;display:none"/>
            </div>
          </div>
        </div>

        <!-- RIGHT: AI extraction results -->
        <div style="display:flex;flex-direction:column;gap:14px;">
          <div class="card">
            <div class="card-header">
              <div class="card-title">🤖 AI ანალიზი</div>
              <span class="card-badge badge-blue" id="ocr-status-badge" style="display:none">Processing...</span>
            </div>
            <div class="card-body" id="ocr-result">
              <div class="empty-state">
                <div class="empty-icon">🔍</div>
                <div class="empty-text">ატვირთე ფაილი ანალიზისთვის</div>
              </div>
            </div>
          </div>
          <!-- Auto-match RS.ge -->
          <div class="card" id="ocr-match-card" style="display:none">
            <div class="card-header">
              <div class="card-title">🔗 Auto-Match RS.ge</div>
              <span class="card-badge badge-amber" id="ocr-match-badge">Checking...</span>
            </div>
            <div class="card-body" id="ocr-match-body"></div>
          </div>
          <!-- Actions -->
          <div class="card" id="ocr-actions-card" style="display:none">
            <div class="card-header"><div class="card-title">⚡ მოქმედებები</div></div>
            <div class="card-body" style="display:flex;gap:10px;flex-wrap:wrap;">
              <button class="btn btn-blue btn-sm" onclick="ocrCreateDraft()">📝 Draft შექმნა</button>
              <button class="btn btn-ghost btn-sm" onclick="ocrDownloadJson()">⬇ JSON</button>
              <button class="btn btn-ghost btn-sm" onclick="ocrReset()">✕ გასუფთავება</button>
            </div>
          </div>
        </div>
      </div>`;
  }

  // ── Public API ────────────────────────────────────────────
  window._ocrData = null;

  window.ocrSplitDrop = function(e) {
    e.preventDefault();
    document.getElementById('ocr-drop-zone')?.classList.remove('uz-drag');
    const file = e.dataTransfer?.files?.[0];
    if (file) _ocrProcess(file);
  };

  window.ocrSplitRun = function(inp) {
    const file = inp?.files?.[0];
    if (file) _ocrProcess(file);
  };

  window.ocrCreateDraft = async function() {
    if (!window._ocrData) return;
    const d = await window.api('/ocr/extract-and-draft', 'POST',
      JSON.stringify(window._ocrData));
    if (d && d.ok) {
      toast('✅ Draft შეიქმნა #' + (d.draft_id || ''), 'ok');
    } else {
      toast('Draft ვერ შეიქმნა', 'err');
    }
  };

  window.ocrDownloadJson = function() {
    if (!window._ocrData) return;
    const blob = new Blob([JSON.stringify(window._ocrData, null, 2)],
      { type: 'application/json' });
    const a = Object.assign(document.createElement('a'),
      { href: URL.createObjectURL(blob), download: 'ocr_result.json' });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  };

  window.ocrReset = function() {
    window._ocrData = null;
    const r = document.getElementById('ocr-result');
    if (r) r.innerHTML = '<div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-text">ატვირთე ფაილი ანალიზისთვის</div></div>';
    ['ocr-preview-card','ocr-match-card','ocr-actions-card'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
    const badge = document.getElementById('ocr-status-badge');
    if (badge) badge.style.display = 'none';
  };

  // ── Internal ──────────────────────────────────────────────
  async function _ocrProcess(file) {
    if (file.size > 10 * 1024 * 1024) { toast('ფაილი 10MB-ზე დიდია', 'err'); return; }

    // Show preview
    _showPreview(file);

    // Show spinner
    const resultEl = document.getElementById('ocr-result');
    const badge = document.getElementById('ocr-status-badge');
    if (resultEl) resultEl.innerHTML = '<div class="loading-row"><span class="spinner"></span> ანალიზი მიმდინარეობს...</div>';
    if (badge) { badge.textContent = 'Processing...'; badge.style.display = ''; }

    try {
      const fd = new FormData();
      fd.append('file', file);

      const r = await fetch(window.BASE + '/ocr/extract', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + window.TOKEN },
        body: fd
      });
      if (!r.ok) throw new Error('OCR API ' + r.status);
      const d = await r.json();
      window._ocrData = d;

      _renderOCRResult(d);
      _checkRsMatch(d);

      if (badge) { badge.textContent = '✅ დასრულდა'; badge.className = 'card-badge badge-green'; }
      const actCard = document.getElementById('ocr-actions-card');
      if (actCard) actCard.style.display = '';
    } catch(e) {
      if (resultEl) resultEl.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div class="empty-text">OCR შეცდომა: ${window.esc ? window.esc(e.message) : e.message}</div></div>`;
      if (badge) { badge.textContent = 'Error'; badge.className = 'card-badge badge-red'; }
    }
  }

  function _showPreview(file) {
    const card = document.getElementById('ocr-preview-card');
    const fname = document.getElementById('ocr-preview-filename');
    const frame = document.getElementById('ocr-pdf-frame');
    const img   = document.getElementById('ocr-img-preview');
    if (!card) return;

    if (fname) fname.textContent = file.name;
    card.style.display = '';

    const url = URL.createObjectURL(file);
    const ext = file.name.split('.').pop().toLowerCase();

    if (ext === 'pdf') {
      if (frame) { frame.src = url; frame.style.display = ''; }
      if (img)   img.style.display = 'none';
    } else if (['png','jpg','jpeg','webp'].includes(ext)) {
      if (img)   { img.src = url; img.style.display = ''; }
      if (frame) frame.style.display = 'none';
    } else {
      card.style.display = 'none';
    }
  }

  function _renderOCRResult(d) {
    const el = document.getElementById('ocr-result');
    if (!el) return;
    const fmt = v => Number(v || 0).toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const esc = window.esc || (s => String(s || '').replace(/</g,'&lt;').replace(/>/g,'&gt;'));

    const lines = d.line_items || d.items || [];
    const info  = d.invoice    || d;

    el.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:12px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
          <div><span style="color:var(--gray-500)">მიმწოდებელი:</span><br><b>${esc(info.supplier || info.vendor || '—')}</b></div>
          <div><span style="color:var(--gray-500)">ინვოის №:</span><br><b>${esc(info.invoice_number || info.number || '—')}</b></div>
          <div><span style="color:var(--gray-500)">თარიღი:</span><br><b>${esc(info.date || info.invoice_date || '—')}</b></div>
          <div><span style="color:var(--gray-500)">სულ:</span><br><b style="color:var(--blue)">${fmt(info.total_amount || info.total)} ₾</b></div>
          ${info.vat_amount ? `<div><span style="color:var(--gray-500)">დღგ:</span><br><b style="color:var(--amber)">${fmt(info.vat_amount)} ₾</b></div>` : ''}
          ${info.net_amount ? `<div><span style="color:var(--gray-500)">ნეტო:</span><br><b>${fmt(info.net_amount)} ₾</b></div>` : ''}
        </div>
        ${lines.length ? `
        <div>
          <div style="font-size:11px;color:var(--gray-500);margin-bottom:6px;font-weight:600">სტრიქონები (${lines.length})</div>
          <table style="width:100%;border-collapse:collapse;font-size:11px">
            <thead><tr style="background:var(--gray-50)">
              <th style="padding:6px 8px;text-align:left;border-bottom:1px solid var(--gray-200)">დასახელება</th>
              <th style="padding:6px 8px;text-align:right;border-bottom:1px solid var(--gray-200)">რ-ბა</th>
              <th style="padding:6px 8px;text-align:right;border-bottom:1px solid var(--gray-200)">ფასი</th>
              <th style="padding:6px 8px;text-align:right;border-bottom:1px solid var(--gray-200)">სულ</th>
            </tr></thead>
            <tbody>
              ${lines.map(l => `<tr>
                <td style="padding:6px 8px;border-bottom:1px solid var(--gray-100)">${esc(l.description || l.name || '—')}</td>
                <td style="padding:6px 8px;border-bottom:1px solid var(--gray-100);text-align:right">${l.quantity ?? 1}</td>
                <td style="padding:6px 8px;border-bottom:1px solid var(--gray-100);text-align:right">${fmt(l.unit_price || l.price)}</td>
                <td style="padding:6px 8px;border-bottom:1px solid var(--gray-100);text-align:right;font-weight:700">${fmt(l.total || l.amount)}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>` : ''}
        ${d.account_code ? `<div style="font-size:12px;padding:8px;background:var(--blue-s);border-radius:8px">
          🧠 AI კლასიფიკაცია: <b>${esc(d.account_code)}</b> — ${esc(d.account_name || '')}
          ${d.confidence ? `<span style="color:var(--gray-400);margin-left:6px">${Math.round(d.confidence * 100)}%</span>` : ''}
        </div>` : ''}
      </div>`;
  }

  async function _checkRsMatch(d) {
    const card  = document.getElementById('ocr-match-card');
    const body  = document.getElementById('ocr-match-body');
    const badge = document.getElementById('ocr-match-badge');
    if (!card) return;

    card.style.display = '';
    // Basic heuristic: if supplier and amount present, suggest checking RS.ge
    const supplier = d.invoice?.supplier || d.supplier || d.vendor || '';
    const total    = d.invoice?.total_amount || d.total_amount || 0;

    if (!supplier && !total) {
      if (badge) { badge.textContent = 'მონ. არ არის'; badge.className = 'card-badge badge-amber'; }
      if (body)  body.innerHTML = '<div style="font-size:12px;color:var(--gray-500)">მიმწოდებელი ან თანხა ვერ ამოიცნო</div>';
      return;
    }

    if (body) body.innerHTML = `
      <div style="font-size:12px;line-height:1.7">
        <div>📋 მიმწოდებელი: <b>${window.esc ? window.esc(supplier) : supplier}</b></div>
        <div>💰 თანხა: <b>${Number(total).toFixed(2)} ₾</b></div>
        <div style="margin-top:8px;padding:8px;background:var(--amber-s,#fffbeb);border-radius:8px;border:1px solid rgba(245,158,11,.2)">
          ⚠️ RS.ge ზედნადების ავტომატური შემოწმება საჭიროებს RS.ge API კავშირს (Settings-ში).
          <br>ხელით შეამოწმე: <a href="https://eservices.rs.ge" target="_blank" style="color:var(--blue)">eservices.rs.ge</a>
        </div>
        <button class="btn btn-ghost btn-sm" style="margin-top:10px" onclick="toast('RS.ge API კავშირი Settings-ში კონფიგურირდება','info')">🔗 RS.ge-ს შეჯერება</button>
      </div>`;
    if (badge) { badge.textContent = 'Manual Check'; badge.className = 'card-badge badge-amber'; }
  }

  // Patch when OCR page is shown
  const _origGoPage = window.goPage;
  if (_origGoPage) {
    window.goPage = function(page, el) {
      _origGoPage(page, el);
      if (page === 'ocr') {
        requestAnimationFrame(_patchOCRPage);
      }
    };
  }

  // Also patch on load if already on OCR page
  document.addEventListener('DOMContentLoaded', () => {
    if (window.curPage === 'ocr') _patchOCRPage();
  });
})();
