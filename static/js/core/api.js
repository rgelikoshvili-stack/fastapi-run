(function () {
  function normalizeBase(base) {
    return String(base || '').replace(/\/$/, '');
  }

  function buildUrl(path) {
    const base = normalizeBase(window.BASE || '');
    if (!path) return base;
    if (/^https?:\/\//i.test(path)) return path;
    return base + (path.startsWith('/') ? path : '/' + path);
  }

  function buildHeaders(extra) {
    const headers = new Headers(extra || {});
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    const token = window.TOKEN || window.token || '';
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', 'Bearer ' + token);
    }
    return headers;
  }

  async function request(path, options) {
    const opts = options || {};
    const method = (opts.method || 'GET').toUpperCase();
    const init = {
      method,
      headers: buildHeaders(opts.headers),
      credentials: opts.credentials || 'same-origin',
    };

    if (opts.body !== undefined) {
      if (typeof opts.body === 'string' || opts.body instanceof FormData || opts.body instanceof Blob || opts.body instanceof ArrayBuffer) {
        init.body = opts.body;
      } else {
        init.body = JSON.stringify(opts.body);
      }
    }

    let response;
    try {
      response = await fetch(buildUrl(path), init);
    } catch (err) {
      const error = new Error('Network error');
      error.cause = err;
      error.networkError = true;
      throw error;
    }

    const contentType = response.headers.get('content-type') || '';
    let payload = null;
    if (contentType.includes('application/json')) {
      try {
        payload = await response.json();
      } catch (_) {
        payload = null;
      }
    } else {
      payload = await response.text();
    }

    if (response.ok) {
      if (payload && typeof payload === 'object' && payload.ok === false) {
        throw buildEnvelopeError(payload, response.status);
      }
      return payload;
    }

    const error = payload && typeof payload === 'object'
      ? buildEnvelopeError(payload, response.status, response.statusText)
      : new Error(response.statusText || 'Request failed');
    if (!error.status) error.status = response.status;
    if (error.body === undefined) error.body = payload;
    if (error.code === undefined) error.code = '';
    error.sessionExpired = response.status === 401;
    error.permissionDenied = response.status === 403;
    error.serverError = response.status >= 500;
    throw error;
  }

  function buildEnvelopeError(payload, status, fallbackMessage) {
    const message = payload && typeof payload === 'object'
      ? (payload.message || payload.error?.details || payload.error?.message || fallbackMessage || 'Request failed')
      : (fallbackMessage || 'Request failed');
    const error = new Error(message);
    error.status = status;
    error.body = payload;
    error.code = payload && typeof payload === 'object' ? (payload.error?.code || '') : '';
    error.sessionExpired = status === 401;
    error.permissionDenied = status === 403;
    error.serverError = status >= 500;
    return error;
  }

  async function get(path, options) {
    return request(path, Object.assign({}, options, { method: 'GET' }));
  }

  async function post(path, body, options) {
    return request(path, Object.assign({}, options, { method: 'POST', body }));
  }

  async function put(path, body, options) {
    return request(path, Object.assign({}, options, { method: 'PUT', body }));
  }

  async function patch(path, body, options) {
    return request(path, Object.assign({}, options, { method: 'PATCH', body }));
  }

  async function del(path, options) {
    return request(path, Object.assign({}, options, { method: 'DELETE' }));
  }

  window.BHApi = Object.freeze({
    request,
    get,
    post,
    put,
    patch,
    delete: del,
    url: buildUrl,
    headers: buildHeaders,
  });
})();
