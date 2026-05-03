import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import './Reports.css';

type Tab = 'pnl' | 'balance' | 'gl';

function fmt(n: number, signed = false) {
  const s = Math.abs(n).toLocaleString('ka-GE', { maximumFractionDigits: 2 });
  if (signed && n < 0) return `-${s}`;
  return s;
}

function PnLReport() {
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [enabled, setEnabled] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['reports', 'pnl', year, month],
    queryFn: () => month
      ? api.get(`/reports/pl?year=${year}&month=${month}`).then(r => r.data)
      : api.get(`/reports/pnl?date_from=${year}-01-01&date_to=${year}-12-31`).then(r => r.data),
    enabled,
    staleTime: 120000,
  });

  const dt = data?.data || {};
  const rev = dt.revenue_detail || dt.revenue_section || {};
  const cogs = dt.cogs_detail || dt.cogs_section || {};
  const opex = dt.opex_detail || dt.opex_section || {};
  const grossP = dt.gross_profit ?? ((dt.revenue ?? 0) - (dt.cogs ?? 0));
  const ebit = dt.ebit ?? dt.net_profit ?? 0;

  return (
    <div>
      <div className="report-toolbar">
        <input type="number" className="input" value={year} onChange={e => setYear(+e.target.value)} style={{ width: 90 }} min={2020} max={2030} />
        <select className="input" value={month} onChange={e => setMonth(+e.target.value)} style={{ width: 140 }}>
          <option value={0}>მთელი წელი</option>
          {['იანვ','თებ','მარ','აპრ','მაი','ივნ','ივლ','აგვ','სექ','ოქტ','ნოე','დეკ'].map((m, i) => (
            <option key={i+1} value={i+1}>{m}</option>
          ))}
        </select>
        <button className="btn btn-primary" onClick={() => setEnabled(true)}>გამოთვლა</button>
      </div>

      {isLoading && <div style={{ textAlign: 'center', padding: 48 }}><span className="spinner" /></div>}
      {data && (
        <div className="pnl-report">
          <div className="pnl-section-block">
            <div className="pnl-section-title">💰 შემოსავალი (Revenue)</div>
            {(rev.lines || []).map((l: any, i: number) => (
              <div key={i} className="pnl-row"><span>{l.label || l.name}</span><span className="pnl-amount text-green">₾{fmt(l.amount)}</span></div>
            ))}
            {!(rev.lines?.length) && <div className="pnl-row text-dim">— 6xxx ცარიელია</div>}
            <div className="pnl-row pnl-subtotal"><span>სულ შემოსავალი</span><span className="pnl-amount">₾{fmt(rev.total ?? dt.revenue ?? 0)}</span></div>
          </div>

          <div className="pnl-section-block">
            <div className="pnl-section-title">🔧 COGS (5xxx)</div>
            {(cogs.lines || []).map((l: any, i: number) => (
              <div key={i} className="pnl-row"><span>{l.label || l.name}</span><span className="pnl-amount text-red">₾{fmt(l.amount)}</span></div>
            ))}
            {!(cogs.lines?.length) && <div className="pnl-row text-dim">— 5xxx ცარიელია</div>}
            <div className="pnl-row pnl-subtotal"><span>სულ COGS</span><span className="pnl-amount">₾{fmt(cogs.total ?? dt.cogs ?? 0)}</span></div>
          </div>

          <div className="pnl-row pnl-gross"><span>📊 Gross Profit</span><span className="pnl-amount">₾{fmt(grossP, true)}</span></div>

          <div className="pnl-section-block">
            <div className="pnl-section-title">💸 OpEx (7xxx)</div>
            {(opex.lines || []).map((l: any, i: number) => (
              <div key={i} className="pnl-row"><span>{l.label || l.name}</span><span className="pnl-amount text-red">₾{fmt(l.amount)}</span></div>
            ))}
            {!(opex.lines?.length) && <div className="pnl-row text-dim">— 7xxx ცარიელია</div>}
            <div className="pnl-row pnl-subtotal"><span>სულ OpEx</span><span className="pnl-amount">₾{fmt(opex.total ?? dt.opex ?? 0)}</span></div>
          </div>

          <div className={`pnl-row pnl-ebit${ebit >= 0 ? ' pnl-ebit-pos' : ' pnl-ebit-neg'}`}>
            <span>🎯 EBIT</span><span className="pnl-amount">₾{fmt(ebit, true)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function BalanceSheet() {
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const [enabled, setEnabled] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['reports', 'balance', asOf],
    queryFn: () => api.get(`/reports/balance-sheet?as_of=${asOf}`).then(r => r.data),
    enabled,
    staleTime: 120000,
  });
  const dt = data?.data || {};

  return (
    <div>
      <div className="report-toolbar">
        <input type="date" className="input" value={asOf} onChange={e => setAsOf(e.target.value)} style={{ width: 160 }} />
        <button className="btn btn-primary" onClick={() => setEnabled(true)}>გამოთვლა</button>
      </div>
      {isLoading && <div style={{ textAlign: 'center', padding: 48 }}><span className="spinner" /></div>}
      {data && (
        <div className="bs-grid">
          {(['assets', 'liabilities', 'equity'] as const).map(k => {
            const sec = dt[k] || {};
            return (
              <div key={k} className="card">
                <div className="pnl-section-title" style={{ marginBottom: 12 }}>
                  {k === 'assets' ? '🏦 აქტივები' : k === 'liabilities' ? '📋 ვალდებულებები' : '💼 კაპიტალი'}
                </div>
                {(sec.lines || []).map((l: any, i: number) => (
                  <div key={i} className="pnl-row"><span>{l.label || l.name}</span><span className="pnl-amount">₾{fmt(l.amount ?? 0)}</span></div>
                ))}
                {!(sec.lines?.length) && <div className="text-dim" style={{ fontSize: 12 }}>ცარიელია</div>}
                <div className="pnl-row pnl-subtotal" style={{ marginTop: 8 }}>
                  <span>სულ</span><span className="pnl-amount">₾{fmt(sec.total ?? 0)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GLReconciliation() {
  const today = new Date().toISOString().slice(0, 10);
  const firstDay = `${new Date().getFullYear()}-01-01`;
  const [from, setFrom] = useState(firstDay);
  const [to, setTo] = useState(today);
  const [enabled, setEnabled] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['reports', 'gl', from, to],
    queryFn: () => api.get(`/reports/gl-reconciliation?date_from=${from}&date_to=${to}`).then(r => r.data),
    enabled,
    staleTime: 120000,
  });
  const rows: any[] = data?.data?.accounts || data?.data || [];

  return (
    <div>
      <div className="report-toolbar">
        <input type="date" className="input" value={from} onChange={e => setFrom(e.target.value)} style={{ width: 148 }} />
        <span className="text-dim">—</span>
        <input type="date" className="input" value={to} onChange={e => setTo(e.target.value)} style={{ width: 148 }} />
        <button className="btn btn-primary" onClick={() => setEnabled(true)}>გამოთვლა</button>
      </div>
      {isLoading && <div style={{ textAlign: 'center', padding: 48 }}><span className="spinner" /></div>}
      {data && (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr><th>ანგარიში</th><th>სახელი</th><th>Debit</th><th>Credit</th><th>ბალანსი</th></tr>
              </thead>
              <tbody>
                {rows.map((r: any, i: number) => (
                  <tr key={i}>
                    <td className="mono">{r.account_code || r.code}</td>
                    <td>{r.name || r.account_name}</td>
                    <td className="num text-green">₾{fmt(r.debit_total ?? r.debit ?? 0)}</td>
                    <td className="num text-red">₾{fmt(r.credit_total ?? r.credit ?? 0)}</td>
                    <td className="num" style={{ fontWeight: 700, color: (r.balance ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      ₾{fmt(r.balance ?? 0, true)}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={5}><div className="empty-state"><div className="empty-ic">📊</div><div className="empty-txt">მონაცემი არ არის</div></div></td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Reports() {
  const [tab, setTab] = useState<Tab>('pnl');

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">Financial Reports</div>
      </div>
      <div className="approval-toolbar">
        <div className="tabs">
          {([['pnl', 'P&L'], ['balance', 'ბალანსი'], ['gl', 'GL Rec.']] as [Tab, string][]).map(([t, label]) => (
            <button key={t} className={`tab-btn${tab === t ? ' tab-btn--active' : ''}`} onClick={() => setTab(t)}>{label}</button>
          ))}
        </div>
      </div>
      {tab === 'pnl' && <PnLReport />}
      {tab === 'balance' && <BalanceSheet />}
      {tab === 'gl' && <GLReconciliation />}
    </div>
  );
}
