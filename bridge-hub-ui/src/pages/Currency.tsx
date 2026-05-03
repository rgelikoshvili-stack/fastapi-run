import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

export default function Currency() {
  const [fromCur, setFromCur] = useState('USD');
  const [toCur, setToCur] = useState('GEL');
  const [amount, setAmount] = useState('100');
  const [converted, setConverted] = useState<any>(null);
  const [converting, setConverting] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['currency', 'rates'],
    queryFn: () => api.get('/currency/rates').then(r => r.data),
    staleTime: 3600000,
  });
  const rates: Record<string, number> = data?.data?.rates || data?.rates || {};
  const updatedAt: string = data?.data?.updated_at || '';

  const convert = async () => {
    setConverting(true);
    const res = await api.get(`/currency/convert?from_currency=${fromCur}&to_currency=${toCur}&amount=${amount}`).catch(() => null);
    setConverted(res?.data?.data || res?.data);
    setConverting(false);
  };

  const currencies = Object.keys(rates);

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <div className="page__title">Currency Rates</div>
          <div className="page__subtitle">Base: GEL · {updatedAt ? `Updated: ${updatedAt.slice(0, 10)}` : 'NBG'}</div>
        </div>
      </div>

      {/* Converter */}
      <div className="card" style={{ maxWidth: 480, marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>კურსის კონვერტერი</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <input className="input" type="number" value={amount} onChange={e => setAmount(e.target.value)} style={{ width: 100 }} />
          <select className="input" value={fromCur} onChange={e => setFromCur(e.target.value)} style={{ width: 100 }}>
            {['GEL', ...currencies].map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <span style={{ lineHeight: '38px', color: 'var(--ink-dim)' }}>→</span>
          <select className="input" value={toCur} onChange={e => setToCur(e.target.value)} style={{ width: 100 }}>
            {['GEL', ...currencies].map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <button className="btn btn-primary" onClick={convert} disabled={converting}>
            {converting ? <span className="spinner" /> : 'კონვ.'}
          </button>
        </div>
        {converted && (
          <div style={{ padding: '12px 16px', background: 'var(--bg)', borderRadius: 8 }}>
            <span style={{ fontSize: 24, fontWeight: 700, color: 'var(--accent)' }}>
              {Number(converted.converted_amount ?? converted.result ?? 0).toLocaleString('ka-GE', { maximumFractionDigits: 4 })} {toCur}
            </span>
            <div style={{ fontSize: 11, color: 'var(--ink-dim)', marginTop: 2 }}>
              1 {fromCur} = {Number(converted.rate ?? 0).toFixed(4)} {toCur}
            </div>
          </div>
        )}
      </div>

      {/* Rates table */}
      <div className="card" style={{ padding: 0, maxWidth: 600 }}>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>ვალუტა</th><th>კურსი (1 = ? GEL)</th><th>GEL → ვალუტა</th></tr></thead>
            <tbody>
              {isLoading ? <tr><td colSpan={3} style={{ textAlign: 'center', padding: 32 }}><span className="spinner" /></td></tr>
                : Object.entries(rates).length === 0
                ? <tr><td colSpan={3}><div className="empty-state"><div className="empty-ic">💱</div><div className="empty-txt">კურსი არ არის</div></div></td></tr>
                : Object.entries(rates).sort(([a], [b]) => a.localeCompare(b)).map(([code, rate]) => (
                  <tr key={code}>
                    <td style={{ fontWeight: 700 }}>{code}</td>
                    <td className="num mono" style={{ color: 'var(--accent)', fontWeight: 600 }}>
                      {Number(rate).toFixed(4)} ₾
                    </td>
                    <td className="num mono text-dim">
                      {rate > 0 ? (1 / rate).toFixed(4) : '—'}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
