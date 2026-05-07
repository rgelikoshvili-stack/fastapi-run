(function () {
  function ensureRoot() {
    let root = document.getElementById('bh-modal-root');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'bh-modal-root';
    document.body.appendChild(root);
    return root;
  }

  function close(id) {
    const node = id ? document.getElementById(id) : document.getElementById('bh-modal-root');
    if (!node) return;
    node.remove();
  }

  function open(config) {
    const opts = config || {};
    const root = ensureRoot();
    root.innerHTML = '';

    const overlay = document.createElement('div');
    overlay.className = 'bh-modal-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9998;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;padding:16px;';

    const panel = document.createElement('div');
    panel.className = 'bh-modal-panel';
    panel.style.cssText = 'width:min(720px,100%);max-height:90vh;overflow:auto;background:#fff;border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,.25);padding:20px;';
    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px;">
        <div style="font-weight:700;font-size:16px;">${opts.title || ''}</div>
        <button type="button" data-bh-close style="background:none;border:none;font-size:22px;line-height:1;cursor:pointer;">&times;</button>
      </div>
      <div data-bh-body>${opts.body || ''}</div>
    `;

    overlay.appendChild(panel);
    root.appendChild(overlay);

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay && opts.closeOnBackdrop !== false) close('bh-modal-root');
    });
    panel.querySelector('[data-bh-close]')?.addEventListener('click', () => close('bh-modal-root'));

    if (typeof opts.onMount === 'function') {
      opts.onMount({ overlay, panel, close: () => close('bh-modal-root') });
    }

    return { overlay, panel, close: () => close('bh-modal-root') };
  }

  function confirm(config) {
    return open(config);
  }

  window.BHModal = Object.freeze({
    open,
    close,
    confirm,
  });
})();
