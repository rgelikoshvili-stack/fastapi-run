import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export default function Settings() {
  const { user } = useAuth();
  const [tab, setTab] = useState<'profile' | 'tenant' | 'security'>('profile');

  const { data: tenantData } = useQuery({
    queryKey: ['tenant', 'info'],
    queryFn: () => api.get('/auth/tenant').then(r => r.data).catch(() => null),
    staleTime: 600000,
  });
  const tenant = tenantData?.data || tenantData || {};

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">Settings</div>
      </div>

      <div className="approval-toolbar">
        <div className="tabs">
          <button className={`tab-btn${tab === 'profile' ? ' tab-btn--active' : ''}`} onClick={() => setTab('profile')}>👤 პროფილი</button>
          <button className={`tab-btn${tab === 'tenant' ? ' tab-btn--active' : ''}`} onClick={() => setTab('tenant')}>🏢 Tenant</button>
          <button className={`tab-btn${tab === 'security' ? ' tab-btn--active' : ''}`} onClick={() => setTab('security')}>🔒 უსაფ.</button>
        </div>
      </div>

      {tab === 'profile' && (
        <div className="card" style={{ maxWidth: 480 }}>
          <div style={{ display: 'flex', flex: 1, flexDirection: 'column', gap: 16 }}>
            {[['ელ-ფოსტა', user?.email || '—'], ['როლი', user?.role || '—'], ['Tenant ID', user?.tenant_id || '—']].map(([l, v]) => (
              <div key={l as string}>
                <div style={{ fontSize: 11, color: 'var(--ink-dim)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>{l}</div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'tenant' && (
        <div className="card" style={{ maxWidth: 480 }}>
          {Object.keys(tenant).length === 0 ? (
            <div className="empty-state"><div className="empty-ic">🏢</div><div className="empty-txt">Tenant info არ არის</div></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {Object.entries(tenant).map(([k, v]: [string, any]) => (
                <div key={k}>
                  <div style={{ fontSize: 11, color: 'var(--ink-dim)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 3 }}>{k.replace(/_/g, ' ')}</div>
                  <div style={{ fontSize: 13 }}>{String(v)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'security' && (
        <div className="card" style={{ maxWidth: 480 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>პაროლის შეცვლა</div>
          <a href="/reset_password.html" className="btn btn-ghost" style={{ display: 'inline-flex' }}>
            პაროლის გადაყენება →
          </a>
          <div style={{ marginTop: 24, fontSize: 13, color: 'var(--ink-soft)' }}>
            Legacy settings available at <a href="/settings.html">settings.html</a>
          </div>
        </div>
      )}
    </div>
  );
}
