import React from 'react';

interface Props {
  title: string;
  icon?: string;
  legacyPath?: string;
}

export default function PlaceholderPage({ title, icon = '🔧', legacyPath }: Props) {
  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">{title}</div>
      </div>
      <div className="card" style={{ textAlign: 'center', padding: '60px 24px' }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>{icon}</div>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>{title}</div>
        <div style={{ color: 'var(--ink-dim)', marginBottom: 24 }}>
          React migration in progress. Use the legacy interface for now.
        </div>
        {legacyPath && (
          <a href={legacyPath} className="btn btn-primary" style={{ display: 'inline-flex' }}>
            Legacy-ზე გადასვლა →
          </a>
        )}
      </div>
    </div>
  );
}
