import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || '',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT from localStorage on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('bh_token');
  if (token) config.headers['Authorization'] = `Bearer ${token}`;
  const tenant = localStorage.getItem('bh_tenant');
  if (tenant) config.headers['X-Tenant-ID'] = tenant;
  return config;
});

// On 401 → clear auth and redirect to login
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('bh_token');
      localStorage.removeItem('bh_refresh');
      window.location.href = '/app/login';
    }
    return Promise.reject(err);
  }
);

export default api;
