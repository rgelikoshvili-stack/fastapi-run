import React, { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import './Login.css';

export default function Login() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (isAuthenticated) return <Navigate to="/app/dashboard" replace />;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { setError('შეიყვანეთ ელ-ფოსტა და პაროლი'); return; }
    setLoading(true);
    setError('');
    try {
      await login(email, password, tenantId || undefined);
      navigate('/app/dashboard', { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.message || err?.response?.data?.detail || 'შესვლა ვერ მოხერხდა');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <svg viewBox="0 0 40 40" fill="none" width="36" height="36">
            <rect width="40" height="40" rx="8" fill="#8c3c2d"/>
            <path d="M8 28 L20 12 L32 28" stroke="#f3ecdc" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
            <path d="M14 22 L26 22" stroke="#f3ecdc" strokeWidth="2.5" strokeLinecap="round"/>
          </svg>
          <span className="login-logo-text">Bridge <em>Hub</em></span>
        </div>

        <h1 className="login-title">შესვლა</h1>
        <p className="login-sub">Bridge Hub · Financial OS</p>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label>ელ-ფოსტა</label>
            <input
              className="input"
              type="email"
              placeholder="you@company.ge"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoFocus
              autoComplete="email"
            />
          </div>
          <div className="login-field">
            <label>პაროლი</label>
            <input
              className="input"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div className="login-field">
            <label>Tenant ID <span style={{ color: 'var(--ink-dim)', fontWeight: 400 }}>(სურვილისამებრ)</span></label>
            <input
              className="input"
              type="text"
              placeholder="default"
              value={tenantId}
              onChange={e => setTenantId(e.target.value)}
            />
          </div>

          {error && <div className="login-error">{error}</div>}

          <button
            type="submit"
            className="btn btn-primary login-btn"
            disabled={loading}
          >
            {loading ? <span className="spinner" /> : 'შესვლა'}
          </button>
        </form>

        <div className="login-foot">
          <a href="/signup.html">ანგარიშის შექმნა</a>
          {' · '}
          <a href="/reset_password.html">პაროლის აღდგენა</a>
        </div>
      </div>
    </div>
  );
}
