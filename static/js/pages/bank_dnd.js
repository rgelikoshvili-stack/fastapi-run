/* Bridge Hub — Bank CSV Drag & Drop Module
   Enhances Bank CSV upload with drag-and-drop, progress bar, auto-process
   Depends on: window.BASE, window.TOKEN, window.TENANT, window.toast, window.api
*/

(function() {
  function _patchBankCSV() {
    const zone = document.getElementById('bank-csv-upload-zone');
    if (!zone || zone.dataset.dndPatched) return;
    zone.dataset.dndPatched = 'true';

    // Replace upload zone with DnD version
    zone.innerHTML = `
      <div id="csv-dnd-area"
        style="border:2px dashed var(--gray-300);border-radius:12px;padding:32px 20px;text-align:center;cursor:pointer;transition:all .2s;"
        ondragover="csvDndOver(event)"
        ondragleave="csvDndLeave(event)"
        ondrop="csvDndDrop(event)"
        onclick="document.getElementById('csv-file-dnd').click()">
        <div style="font-size:36px;margin-bottom:10px">🏦</div>
        <div style="font-size:14px;font-weight:600;color:var(--gray-700)">CSV / XLSX ჩამოაგდე ან დააჭირე</div>
        <div style="font-size:11px;color:var(--gray-400);margin-top:6px">TBC · BOG · ნებისმიერი ბანკი · მაქს. 5MB</div>
        <input type="file" id="csv-file-dnd" style="display:none"
          accept=".csv,.xlsx,.xls" onchange="csvFileSelected(this)"/>
      </div>
      <div id="csv-progress-wrap" style="display:none;margin-top:12px">
        <div style="font-size:11px;color:var(--gray-500);margin-bottom:4px" id="csv-progress-label">ატვირთვა...</div>
        <div style="background:var(--gray-200);border-radius:6px;height:6px;overflow:hidden">
          <div id="csv-progress-bar" style="height:100%;background:var(--blue);transition:width .3s;width:0%"></div>
        </div>
      </div>
      <div id="csv-result-area" style="margin-top:12px"></div>`;
  }

  window.csvDndOver = function(e) {
    e.preventDefault();
    const area = document.getElementById('csv-dnd-area');
    if (area) {
      area.style.borderColor  = 'var(--blue)';
      area.style.background   = 'var(--blue-s)';
    }
  };

  window.csvDndLeave = function(e) {
    const area = document.getElementById('csv-dnd-area');
    if (area) {
      area.style.borderColor = 'var(--gray-300)';
      area.style.background  = '';
    }
  };

  window.csvDndDrop = function(e) {
    e.preventDefault();
    csvDndLeave(e);
    const file = e.dataTransfer?.files?.[0];
    if (file) _processCSV(file);
  };

  window.csvFileSelected = function(inp) {
    const file = inp?.files?.[0];
    if (file) _processCSV(file);
  };

  async function _processCSV(file) {
    if (file.size > 5 * 1024 * 1024) { toast('ფაილი 5MB-ზე დიდია', 'err'); return; }

    const ext = file.name.split('.').pop().toLowerCase();
    if (!['csv','xlsx','xls'].includes(ext)) {
      toast('მხოლოდ CSV ან XLSX', 'err'); return;
    }

    const label = document.getElementById('csv-progress-label');
    const bar   = document.getElementById('csv-progress-bar');
    const wrap  = document.getElementById('csv-progress-wrap');
    const res   = document.getElementById('csv-result-area');

    if (wrap)  wrap.style.display  = '';
    if (bar)   bar.style.width     = '20%';
    if (label) label.textContent   = `⬆ ატვირთვა: ${file.name}`;
    if (res)   res.innerHTML       = '';

    toast(`📋 ${file.name} ატვირთვა...`, 'info');

    try {
      // Step 1: Upload
      const fd1 = new FormData();
      fd1.append('file', file);
      if (bar) bar.style.width = '40%';

      const r1 = await fetch(window.BASE + '/bank-csv/upload', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + window.TOKEN },
        body: fd1
      });
      if (!r1.ok) throw new Error('Upload failed: ' + r1.status);
      const d1 = await r1.json();

      if (bar)   bar.style.width   = '60%';
      if (label) label.textContent = '⚙ დამუშავება...';

      // Step 2: Process
      const fileId = d1.data?.file_id || d1.file_id || d1.data?.id;
      if (!fileId) throw new Error('file_id ვერ მოვიძიე');

      const r2 = await fetch(window.BASE + '/bank-csv/process', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + window.TOKEN,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ file_id: fileId })
      });
      if (!r2.ok) throw new Error('Process failed: ' + r2.status);
      const d2 = await r2.json();

      if (bar)   bar.style.width   = '100%';
      if (label) label.textContent = '✅ დასრულდა';

      _renderCSVResult(d2, res);
      toast(`✅ ${file.name} — ${d2.data?.created || d2.created || 0} draft შეიქმნა`, 'ok');

    } catch(err) {
      if (bar)   bar.style.width   = '100%';
      if (bar)   bar.style.background = 'var(--red)';
      if (label) label.textContent = '❌ შეცდომა';
      if (res)   res.innerHTML = `<div style="color:var(--red);font-size:12px;margin-top:8px">❌ ${err.message}</div>`;
      toast('CSV შეცდომა: ' + err.message, 'err');
    }
  }

  function _renderCSVResult(d, container) {
    if (!container) return;
    const rows = d.data?.rows || d.rows || [];
    const esc  = window.esc || (s => String(s||'').replace(/</g,'&lt;').replace(/>/g,'&gt;'));

    container.innerHTML = `
      <div style="font-size:12px">
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px">
          <div style="padding:10px;background:var(--green-s);border-radius:8px;text-align:center">
            <div style="font-size:18px;font-weight:700;color:var(--green)">${d.data?.created || d.created || 0}</div>
            <div style="color:var(--gray-500)">Draft შეიქმნა</div>
          </div>
          <div style="padding:10px;background:var(--blue-s);border-radius:8px;text-align:center">
            <div style="font-size:18px;font-weight:700;color:var(--blue)">${d.data?.total || d.total || rows.length}</div>
            <div style="color:var(--gray-500)">სულ ოპ.</div>
          </div>
          <div style="padding:10px;background:var(--amber-s,#fffbeb);border-radius:8px;text-align:center">
            <div style="font-size:18px;font-weight:700;color:var(--amber,#d97706)">${d.data?.skipped || d.skipped || 0}</div>
            <div style="color:var(--gray-500)">გამოტ.</div>
          </div>
        </div>
        ${rows.length ? `<table style="width:100%;border-collapse:collapse">
          <thead><tr style="background:var(--gray-50)">
            <th style="padding:6px 8px;text-align:left;font-size:11px">თარიღი</th>
            <th style="padding:6px 8px;text-align:left;font-size:11px">აღწერა</th>
            <th style="padding:6px 8px;text-align:right;font-size:11px">თანხა</th>
            <th style="padding:6px 8px;text-align:left;font-size:11px">ანგ.</th>
          </tr></thead>
          <tbody>${rows.slice(0, 10).map(r => `<tr>
            <td style="padding:5px 8px;border-bottom:1px solid var(--gray-100);font-size:11px">${esc(r.date||'')}</td>
            <td style="padding:5px 8px;border-bottom:1px solid var(--gray-100);font-size:11px">${esc(String(r.description||r.desc||'').slice(0,40))}</td>
            <td style="padding:5px 8px;border-bottom:1px solid var(--gray-100);font-size:11px;text-align:right;font-weight:700;color:${(r.amount||0)>=0?'var(--green)':'var(--red)'}">${Number(r.amount||0).toFixed(2)} ₾</td>
            <td style="padding:5px 8px;border-bottom:1px solid var(--gray-100);font-size:11px;font-family:var(--mono)">${esc(r.account_code||'—')}</td>
          </tr>`).join('')}</tbody>
        </table>
        ${rows.length > 10 ? `<div style="text-align:center;padding:8px;color:var(--gray-400);font-size:11px">... კიდევ ${rows.length - 10} ოპ.</div>` : ''}` : ''}
      </div>`;
  }

  // Hook into Bank page
  const _origGoPage = window.goPage;
  if (_origGoPage) {
    window.goPage = function(page, el) {
      _origGoPage(page, el);
      if (page === 'bank') requestAnimationFrame(_tryPatchBankSection);
    };
  }

  function _tryPatchBankSection() {
    // Check if bank-csv-upload-zone already exists from bank CSV page
    const zone = document.getElementById('bank-csv-upload-zone');
    if (zone) { _patchBankCSV(); return; }

    // Otherwise try to patch the existing bank-csv page
    const bcPage = document.getElementById('pg-bankcsv') || document.getElementById('pg-bank');
    if (!bcPage || bcPage.dataset.dndBankPatched) return;
    bcPage.dataset.dndBankPatched = 'true';

    // Find upload card and inject DnD zone
    const uploadCards = bcPage.querySelectorAll('.card');
    uploadCards.forEach(card => {
      const title = card.querySelector('.card-title');
      if (title && (title.textContent.includes('CSV') || title.textContent.includes('Upload'))) {
        const body = card.querySelector('.card-body');
        if (body && !body.dataset.dndPatched) {
          body.dataset.dndPatched = 'true';
          body.id = 'bank-csv-upload-zone';
          _patchBankCSV();
        }
      }
    });
  }

  document.addEventListener('DOMContentLoaded', _tryPatchBankSection);
})();
