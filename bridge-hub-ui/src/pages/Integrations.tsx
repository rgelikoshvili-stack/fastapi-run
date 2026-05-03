import React from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

interface IntegrationStatus {
  name: string;
  status: 'connected' | 'disconnected' | 'error';
  last_sync?: string;
  details?: string;
}

const INTEGRATIONS = [
  { key: 'nbg', label: 'NBG (National Bank)', icon: '🏦', endpoint: '/currency/rates' },
  { key: 'email', label: 'Email Collector', icon: '📧', endpoint: '/email-collector/status' },
  { key: 'gcs', label: 'Google Cloud Storage', icon: '☁️', endpoint: '/documents?limit=1' },
];

function IntegrationCard({ label, icon, endpoint }: { label: string; icon: string; endpoint: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['integration', endpoint],
    queryFn: () => api.get(endpoint).then(r => r.data),
    staleTime: 120000,
    retry: 1,
  });

  const ok = !isError && data?.ok !== false;
  const statusColor = isLoading ? 'var(--ink-dim)' : ok ? 'var(--green)' : 'var(--red)';
  const statusText = isLoading ? 'Checking...' : ok ? 'Connected' : 'Error';

  return (
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ fontSize: 32 }}>{icon}</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, fontSize: 14 }}>{label}</div>
        <div style={{ fontSize: 12, color: 'var(--ink-dim)', marginTop: 2 }}>{endpoint}</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: statusColor, fontWeight: 600, fontSize: 13 }}>
        {isLoading ? <span className="spinner" /> : (
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, display: 'inline-block' }} />
        )}
        {statusText}
      </div>
    </div>
  );
}

export default function Integrations() {
  return (
    <div className="page">
      <div className="page__header">
        <div>
          <div className="page__title">Integrations</div>
          <div className="page__subtitle">გარე სერვისების სტატუსი</div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 600 }}>
        {INTEGRATIONS.map(({ key, label, icon, endpoint }) => (
          <IntegrationCard key={key} label={label} icon={icon} endpoint={endpoint} />
        ))}
      </div>

      <div style={{ marginTop: 24 }}>
        <a href="/integrations.html" className="btn btn-ghost" style={{ display: 'inline-flex' }}>
          სრული კონფიგურაცია (Legacy) →
        </a>
      </div>
    </div>
  );
}
