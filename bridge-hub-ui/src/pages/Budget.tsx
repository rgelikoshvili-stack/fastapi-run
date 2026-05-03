import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

function fmt(n: number) { return Number(n || 0).toLocaleString('ka-GE', { maximumFractionDigits: 0 }); }
function pct(a: number, b: number) { return b ? Math.round((a / b) * 100) : 0; }

type Tab = 'vsactual' | 'list' | 'forecast';

export default function Budget() {
  const [tab, setTab] = useState<Tab>('vsactual');
  const [year, setYear] = useState(new Date().getFullYear());

  const { data: vsData, isLoading: vsLoading } = useQuery({
    queryKey: ['budget', 'vsactual', year],
    queryFn: () => api.get(`/budget/vs-actual/${year}`).then(r => r.data),
    enabled: tab === 'vsactual',
    staleTime: 120000,
  });

  const { data: listData, isLoading: listLoading } = useQuery({
    queryKey: ['budget', 'list', year],
    queryFn: () => api.get(`/budget/list/${year}`).then(r => r.data),
    enabled: tab === 'list',
    staleTime: 120000,
  });

  const { data: forecastData, isLoading: forecastLoading } = useQuery({
    queryKey: ['budget', 'forecast', year],
    queryFn: () => api.get(`/budget/forecast/${year}`).then(r => r.data),
    enabled: tab === 'forecast',
    staleTime: 120000,
  });

  const vsRows: any[] = vsData?.data?.items || vsData?.items || vsData?.data || [];
  const listRows: any[] = listData?.data?.items || listData?.items || listData?.data || [];
  const forecastRows: any[] = forecastData?.data?.months || forecastData?.months || forecastData?.data || [];

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <div className="page__title">Budget Planning</div>
          <div className="page__subtitle">ბიუჯეტი vs. ფაქტი</div>
        </div>
        <input type="number" className="input" value={year} onChange={e => setYear(+e.target.value)} style={{ width: 90 }} min={2020} max={2030} />
      </div>

      <div className="approval-toolbar">
        <div className="tabs">
          <button className={`tab-btn${tab === 'vsactual' ? ' tab-btn--active' : ''}`} onClick={() => setTab('vsactual')}>📊 Bud. vs Actual</button>
          <button className={`tab-btn${tab === 'list' ? ' tab-btn--active' : ''}`} onClick={() => setTab('list')}>📋 ბიუჯეტი</button>
          <button className={`tab-btn${tab === 'forecast' ? ' tab-btn--active' : ''}`} onClick={() => setTab('forecast')}>🔮 პროგნოზი</button>
        </div>
      </div>

      {tab === 'vsactual' && (
        <div className="card" style={{ padding: 0 }}>
          {vsLoading ? <div style={{ textAlign: 'center', padding: 48 }}><span className="spinner" /></div> : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>კატეგორია</th><th>ბიუჯეტი</th><th>ფაქტი</th><th>სხვაობა</th><th>%</th></tr></thead>
                <tbody>
                  {vsRows.length === 0 ? <tr><td colSpan={5}><div className="empty-state"><div className="empty-ic">📊</div><div className="empty-txt">ბიუჯეტი არ არის</div></div></td></tr>
                    : vsRows.map((r: any, i: number) => {
                      const diff = (r.actual ?? 0) - (r.budget ?? 0);
                      const p = pct(r.actual ?? 0, r.budget ?? 1);
                      return (
                        <tr key={i}>
                          <td style={{ fontWeight: 600 }}>{r.category || r.name}</td>
                          <td className="num">₾{fmt(r.budget)}</td>
                          <td className="num">₾{fmt(r.actual)}</td>
                          <td className="num" style={{ color: diff >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                            {diff >= 0 ? '+' : ''}₾{fmt(diff)}
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <div style={{ flex: 1, height: 6, background: 'var(--line)', borderRadius: 3 }}>
                                <div style={{ width: `${Math.min(p, 100)}%`, height: '100%', background: p > 100 ? 'var(--red)' : 'var(--green)', borderRadius: 3 }} />
                              </div>
                              <span style={{ fontSize: 11, width: 36, textAlign: 'right', color: 'var(--ink-dim)' }}>{p}%</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'list' && (
        <div className="card" style={{ padding: 0 }}>
          {listLoading ? <div style={{ textAlign: 'center', padding: 48 }}><span className="spinner" /></div> : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>კატეგ.</th><th>პერიოდი</th><th>ბიუჯეტი</th><th>ფაქტი</th><th>სტ.</th></tr></thead>
                <tbody>
                  {listRows.length === 0 ? <tr><td colSpan={5}><div className="empty-state"><div className="empty-ic">📋</div><div className="empty-txt">ცარიელია</div></div></td></tr>
                    : listRows.map((r: any, i: number) => (
                      <tr key={i}>
                        <td>{r.category || r.account_name}</td>
                        <td className="mono text-dim" style={{ fontSize: 12 }}>{r.period || `${r.year}-${String(r.month || '').padStart(2, '0')}`}</td>
                        <td className="num">₾{fmt(r.budget_amount || r.budget)}</td>
                        <td className="num">₾{fmt(r.actual_amount || r.actual)}</td>
                        <td><span className="badge badge-approved">active</span></td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'forecast' && (
        <div className="card" style={{ padding: 0 }}>
          {forecastLoading ? <div style={{ textAlign: 'center', padding: 48 }}><span className="spinner" /></div> : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>თვე</th><th>პროგნოზ. შემ.</th><th>პროგნოზ. ხარ.</th><th>პროგნოზ. მოგ.</th></tr></thead>
                <tbody>
                  {forecastRows.length === 0 ? <tr><td colSpan={4}><div className="empty-state"><div className="empty-ic">🔮</div><div className="empty-txt">ცარიელია</div></div></td></tr>
                    : forecastRows.map((r: any, i: number) => (
                      <tr key={i}>
                        <td>{r.month || r.period}</td>
                        <td className="num text-green">₾{fmt(r.revenue || r.forecast_revenue)}</td>
                        <td className="num text-red">₾{fmt(r.expenses || r.forecast_expenses)}</td>
                        <td className="num" style={{ fontWeight: 700, color: ((r.revenue ?? 0) - (r.expenses ?? 0)) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                          ₾{fmt((r.revenue || 0) - (r.expenses || 0))}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
