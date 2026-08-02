window.BridgeHub = window.BridgeHub || {};

/*
  Bridge Hub — Sidebar
  Structured for Georgian financial & accounting software.
  Sections follow standard accounting workflow order.
*/
const _BH_SIDEBAR_HTML = `
<div class="brand">
  <div class="logo">B</div>
  <div style="min-width:0;flex:1">
    <div class="bname">Bridge <em>Hub</em></div>
    <div class="brole">Financial OS</div>
  </div>
</div>

<nav class="nav" id="bh-nav">

  <!-- ─── მთავარი ─────────────────────────────── -->
  <div class="sec">მთავარი</div>
  <div class="item" data-page="dashboard" onclick="location.href='/static/approval.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M3 12l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>
    <span class="lbl">Dashboard</span>
  </div>
  <div class="item" data-page="queue" onclick="location.href='/static/drafts.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
    <span class="lbl">დასამტკიცებელი</span>
    <span class="badge" id="bh-pending-count" style="display:none">0</span>
  </div>

  <!-- ─── დოკუმენტები ──────────────────────────── -->
  <div class="sec">დოკუმენტები</div>
  <div class="item" data-page="inbox" onclick="location.href='/static/documents.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
    <span class="lbl">Documents Hub</span>
  </div>
  <div class="item" data-page="invoices" onclick="location.href='/static/outgoing_form.html'">
    <svg class="ic" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 10h8M8 14h5"/><path d="M15 14v4"/><path d="M15 18h3"/></svg>
    <span class="lbl">გამავალი ინვოისი</span>
  </div>
  <div class="item" data-page="tax" onclick="location.href='/static/tax_invoices.html'">
    <svg class="ic" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/><path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/></svg>
    <span class="lbl">საგ. ინვოისები</span>
  </div>
  <div class="item" data-page="waybills" onclick="location.href='/static/waybills.html'">
    <svg class="ic" viewBox="0 0 24 24"><rect x="1" y="3" width="15" height="13" rx="1"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
    <span class="lbl">ზედნადებები</span>
  </div>

  <!-- ─── ბუღალტერია ───────────────────────────── -->
  <div class="sec">ბუღალტერია</div>
  <div class="item" data-page="journal" onclick="location.href='/static/journal.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
    <span class="lbl">ჟურნალი</span>
  </div>
  <div class="item" data-page="ledger" onclick="location.href='/static/ledger.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
    <span class="lbl">ანგარიშის ბარათი</span>
  </div>
  <div class="item" data-page="trial" onclick="location.href='/static/trial_balance.html'">
    <svg class="ic" viewBox="0 0 24 24"><line x1="12" y1="2" x2="12" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
    <span class="lbl">საცდელი ბალანსი</span>
  </div>
  <div class="item" data-page="counterparty" onclick="location.href='/static/counterparty_ledger.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
    <span class="lbl">კონტრაგენტები</span>
  </div>
  <div class="item" data-page="tools" onclick="location.href='/static/accounting_tools.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M12 22V12"/><path d="M5 17H2a10 10 0 0 0 20 0h-3"/><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
    <span class="lbl">Period Close</span>
  </div>

  <!-- ─── ანგარიშები ───────────────────────────── -->
  <div class="sec">ანგარიშები</div>
  <div class="item" data-page="financial" onclick="location.href='/static/financial_reports.html'">
    <svg class="ic" viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
    <span class="lbl">ფინ. ანგარიშები</span>
  </div>
  <div class="item" data-page="reports" onclick="location.href='/static/reports.html'">
    <svg class="ic" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
    <span class="lbl">Reporting Hub</span>
  </div>
  <div class="item" data-page="aging" onclick="location.href='/static/aging_report.html'">
    <svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
    <span class="lbl">AR/AP Aging</span>
  </div>

  <!-- ─── გაყიდვები & შესყიდვები ──────────────── -->
  <div class="sec">ვაჭრობა</div>
  <div class="item" data-page="purchases" onclick="location.href='/static/purchases_sales.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M3 6h18l-2 7H6z"/><circle cx="9" cy="19" r="1.5"/><circle cx="17" cy="19" r="1.5"/><path d="M7 6l1-3h8l1 3"/></svg>
    <span class="lbl">Purchases &amp; Sales</span>
  </div>

  <!-- ─── გადასახადები ──────────────────────────── -->
  <div class="sec">გადასახადები</div>
  <div class="item" data-page="vat" onclick="location.href='/static/vat_declaration.html'">
    <svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/><path d="M12 8v8"/></svg>
    <span class="lbl">VAT დეკლარაცია</span>
  </div>

  <!-- ─── ხელფასი ───────────────────────────────── -->
  <div class="sec">ხელფასი</div>
  <div class="item" data-page="employees" onclick="location.href='/static/employees.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
    <span class="lbl">თანამშრომლები</span>
  </div>
  <div class="item" data-page="payroll" onclick="location.href='/static/payroll_ledger.html'">
    <svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v10M9 10h4.5a1.5 1.5 0 010 3H10"/></svg>
    <span class="lbl">Payroll Ledger</span>
  </div>

  <!-- ─── ოპერაციები ───────────────────────────── -->
  <div class="sec">ოპერაციები</div>
  <div class="item" data-page="inventory" onclick="location.href='/static/inventory.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
    <span class="lbl">Inventory</span>
  </div>
  <div class="item" data-page="assets" onclick="location.href='/static/fixed_assets.html'">
    <svg class="ic" viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/><line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/></svg>
    <span class="lbl">ძირ. საშუალებები</span>
  </div>
  <div class="item" data-page="budget" onclick="location.href='/static/budget_planning.html'">
    <svg class="ic" viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
    <span class="lbl">ბიუჯეტი</span>
  </div>

  <!-- ─── სისტემა ───────────────────────────────── -->
  <div class="sec">სისტემა</div>
  <div class="item" data-page="settings" onclick="location.href='/static/settings.html'">
    <svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
    <span class="lbl">Settings</span>
  </div>
  <div class="item" data-page="integrations" onclick="location.href='/static/integrations.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
    <span class="lbl">Integrations</span>
  </div>
  <div class="item" data-page="audit" onclick="location.href='/static/audit_dashboard.html'">
    <svg class="ic" viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
    <span class="lbl">Audit Log</span>
  </div>
  <div class="item" data-page="ai" onclick="location.href='/static/ai_control.html'">
    <svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M4.93 19.07l2.12-2.12M16.95 7.05l2.12-2.12"/></svg>
    <span class="lbl">AI Control</span>
  </div>
  <div class="item" data-page="patterns" onclick="location.href='/static/patterns_dashboard.html'">
    <svg class="ic" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
    <span class="lbl">AI Patterns</span>
  </div>

</nav>

<div class="foot">
  <div class="av" id="bh-user-av">R</div>
  <div style="min-width:0;flex:1">
    <div class="uname" id="bh-user-name">—</div>
    <div class="urole" id="bh-user-tenant">—</div>
  </div>
</div>
`;

BridgeHub.loadSidebar = function(currentPage) {
    const mount = document.getElementById('sidebar-mount');
    if (!mount) return;
    mount.innerHTML = _BH_SIDEBAR_HTML;
    BridgeHub._markActive(currentPage);
    BridgeHub._loadUserInfo();
    BridgeHub._loadPendingCount();
};

BridgeHub._markActive = function(pageName) {
    document.querySelectorAll('#bh-nav .item').forEach(el => {
        el.classList.toggle('active', el.dataset.page === pageName);
    });
};

BridgeHub._loadUserInfo = function() {
    try {
        const token = localStorage.getItem('access_token');
        if (!token) return;
        const payload = JSON.parse(atob(token.split('.')[1]));
        const name = document.getElementById('bh-user-name');
        const tenant = document.getElementById('bh-user-tenant');
        const av = document.getElementById('bh-user-av');
        if (name) name.textContent = payload.email || payload.sub || '—';
        if (tenant) tenant.textContent = payload.tenant_id || '—';
        if (av) av.textContent = (payload.email || 'U')[0].toUpperCase();
    } catch (_) {}
};

BridgeHub._loadPendingCount = async function() {
    try {
        const token = localStorage.getItem('access_token');
        if (!token) return;
        const res = await fetch('/approval/queue?limit=0', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (!res.ok) return;
        const data = await res.json();
        const count = data.total || data.count || (Array.isArray(data.drafts) ? data.drafts.length : 0);
        const badge = document.getElementById('bh-pending-count');
        if (badge && count > 0) {
            badge.textContent = count;
            badge.style.display = '';
        }
    } catch (_) {}
};
