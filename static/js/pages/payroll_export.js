/* Bridge Hub — Payroll Export Module
   Adds: Excel export, RS.ge XML, Payroll Drafts generation
   Depends on: window.BASE, window.TOKEN, window.TENANT, window.toast, window.api
*/

async function exportPayrollExcel() {
  if (!window.TOKEN) { toast('ავტორიზაცია საჭიროა', 'err'); return; }
  toast('📊 Excel ემზადება...', 'info');
  try {
    const r = await fetch(window.BASE + '/payroll/history?limit=200', {
      headers: { 'Authorization': 'Bearer ' + window.TOKEN }
    });
    if (!r.ok) { toast('Payroll history ვერ ჩაიტვირთა', 'err'); return; }
    const d = await r.json();
    const rows = d.data?.items || d.items || [];
    if (!rows.length) { toast('მონაცემი არ არის', 'warn'); return; }

    // Build CSV (Excel-compatible UTF-8 BOM)
    const BOM = '\uFEFF';
    const header = ['თარიღი','თანამშრომელი','Gross','Net','PIT 20%','PAYG 2%','სტატუსი'];
    const lines  = rows.map(r => [
      r.period || r.created_at?.slice(0,10) || '',
      r.employee_name || '',
      r.gross_salary  || 0,
      r.net_salary    || 0,
      r.pit_20pct     || 0,
      r.payg_2pct     || 0,
      r.status        || 'generated'
    ].join(','));

    const csv = BOM + [header.join(','), ...lines].join('\r\n');
    _downloadBlob(csv, 'text/csv;charset=utf-8', `payroll_${_month()}.csv`);
    toast('📊 Payroll Excel გადმოიწერა ✅', 'ok');
  } catch(e) { toast('Export შეცდომა: ' + e.message, 'err'); }
}

async function exportPayrollRsXml() {
  if (!window.TOKEN) { toast('ავტორიზაცია საჭიროა', 'err'); return; }
  toast('📋 RS.ge XML ემზადება...', 'info');
  try {
    const rows = _collectPayrollRows();
    if (!rows.length) { toast('ჯერ გააანგარიშე Payroll', 'warn'); return; }

    const period = _month();
    let xml = `<?xml version="1.0" encoding="UTF-8"?>\n<Declaration period="${period}" type="income_tax">\n`;
    rows.forEach(emp => {
      xml += `  <Employee>\n`;
      xml += `    <Name>${_xmlEsc(emp.name)}</Name>\n`;
      xml += `    <PersonalID>${_xmlEsc(emp.personalId)}</PersonalID>\n`;
      xml += `    <Gross>${emp.gross.toFixed(2)}</Gross>\n`;
      xml += `    <PIT>${emp.pit.toFixed(2)}</PIT>\n`;
      xml += `    <PAYG>${emp.payg.toFixed(2)}</PAYG>\n`;
      xml += `    <Net>${emp.net.toFixed(2)}</Net>\n`;
      xml += `  </Employee>\n`;
    });
    xml += `</Declaration>`;

    _downloadBlob(xml, 'application/xml;charset=utf-8', `rs_ge_payroll_${period}.xml`);
    toast('📋 RS.ge XML გადმოიწერა ✅', 'ok');
  } catch(e) { toast('XML შეცდომა: ' + e.message, 'err'); }
}

async function generatePayrollDrafts() {
  const rows = _collectPayrollRows();
  if (!rows.length) { toast('ჯერ გააანგარიშე Payroll', 'warn'); return; }
  toast('📝 Journal drafts იქმნება...', 'info');
  const d = await window.api('/payroll/generate-drafts', 'POST', {
    employees: rows.map(r => ({ name: r.name, gross_salary: r.gross, position: 'employee' }))
  });
  if (d && d.ok) {
    toast(`✅ ${d.created || rows.length} draft შეიქმნა`, 'ok');
  } else {
    toast('Draft-ები ვერ შეიქმნა', 'err');
  }
}

// ── helpers ──────────────────────────────────────────────────
function _collectPayrollRows() {
  const tbody = document.getElementById('payrollBody');
  if (!tbody) return [];
  return Array.from(tbody.querySelectorAll('tr')).map(tr => {
    const name     = tr.querySelector('.emp-name')?.value?.trim()    || '';
    const personalId = tr.querySelector('.emp-id-number')?.value?.trim() || '';
    const gross    = parseFloat(tr.querySelector('.emp-gross')?.value || 0);
    const net      = parseFloat(tr.querySelector('.emp-net')?.value   || 0);
    const pit      = gross * 0.20;
    const payg     = gross * 0.02;
    return { name, personalId, gross, net, pit, payg };
  }).filter(r => r.name && r.gross > 0);
}

function _downloadBlob(content, mime, filename) {
  const blob = new Blob([content], { type: mime });
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function _month() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
}

function _xmlEsc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
