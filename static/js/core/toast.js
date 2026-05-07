(function () {
  function ensureRoot() {
    let root = document.getElementById('bh-toast-root');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'bh-toast-root';
    root.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:10000;display:flex;flex-direction:column;gap:8px;pointer-events:none;';
    document.body.appendChild(root);
    return root;
  }

  function show(message, type, duration) {
    const root = ensureRoot();
    const el = document.createElement('div');
    const variant = type || 'info';
    const timeout = typeof duration === 'number' ? duration : 2600;
    el.style.cssText = 'pointer-events:auto;max-width:360px;padding:10px 12px;border-radius:10px;font-size:13px;line-height:1.4;box-shadow:0 10px 28px rgba(0,0,0,.18);background:#1a1512;color:#f3ecdc;';
    if (variant === 'ok' || variant === 'success') el.style.background = '#27500A';
    if (variant === 'warn' || variant === 'warning') el.style.background = '#b57d1a';
    if (variant === 'err' || variant === 'error') el.style.background = '#a83828';
    el.textContent = String(message || '');
    root.appendChild(el);
    window.setTimeout(() => el.remove(), timeout);
    return el;
  }

  window.BHToast = Object.freeze({
    show,
  });

  if (typeof window.toast !== 'function') {
    window.toast = show;
  }
})();
