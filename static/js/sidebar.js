window.BridgeHub = window.BridgeHub || {};

BridgeHub.loadSidebar = async function(currentPage) {
    const mount = document.getElementById('sidebar-mount');
    if (!mount) return;
    try {
        const res = await fetch('/static/components/sidebar.html');
        if (!res.ok) throw new Error('sidebar fetch failed');
        mount.innerHTML = await res.text();
        BridgeHub._markActive(currentPage);
        BridgeHub._loadUserInfo();
        BridgeHub._loadPendingCount();
    } catch (e) {
        console.warn('[BridgeHub] sidebar load error:', e);
    }
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
