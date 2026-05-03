import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import api from '../api/client';
import type { KPI, PnL, CashflowChart } from '../api/types';
import './Dashboard.css';

function KpiCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div className="kpi-card card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { data: kpiRes, isLoading: kpiLoading } = useQuery({
    queryKey: ['dashboard', 'kpi'],
    queryFn: () => api.get('/dashboard/live/kpi').then(r => r.data),
    refetchInterval: 60000,
    staleTime: 30000,
  });

  const { data: pnlRes, isLoading: pnlLoading } = useQuery({
    queryKey: ['dashboard', 'pnl'],
    queryFn: () => api.get('/dashboard/live/pnl?period=month').then(r => r.data),
    refetchInterval: 60000,
    staleTime: 30000,
  });

  const { data: cfRes, isLoading: cfLoading } = useQuery({
    queryKey: ['dashboard', 'cashflow'],
    queryFn: () => api.get('/dashboard/live/cashflow?days=30').then(r => r.data),
    refetchInterval: 60000,
    staleTime: 30000,
  });

  const kpi: KPI | undefined = kpiRes?.kpi;
  const pnl: PnL | undefined = pnlRes?.pnl;
  const cfChart: CashflowChart | undefined = cfRes?.chart;

  const cfData = cfChart
    ? cfChart.labels.map((label: string, i: number) => ({
        date: label,
        inflow: cfChart.inflow[i] || 0,
        outflow: cfChart.outflow[i] || 0,
      }))
    : [];

  const fmt = (n?: number) => n != null ? n.toLocaleString('ka-GE', { maximumFractionDigits: 0 }) : '—';
  const pct = (n?: number) => n != null ? `${n.toFixed(1)}%` : '—';

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <div className="page__title">Dashboard</div>
          <div className="page__subtitle">Bridge Hub · Financial Overview</div>
        </div>
        <div className="dash-live-badge">
          <span className="live-dot" />
          Live
        </div>
      </div>

      {/* KPI Grid */}
      <div className="kpi-grid">
        {kpiLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="kpi-card card kpi-skeleton" />
          ))
        ) : (
          <>
            <KpiCard label="სულ დრაფტი" value={fmt(kpi?.total_drafts)} />
            <KpiCard label="მოლოდინში" value={fmt(kpi?.pending)} color="var(--yellow)" />
            <KpiCard label="დამტკიცებული" value={fmt((kpi?.approved ?? 0) + (kpi?.auto_approved ?? 0))} color="var(--green)" />
            <KpiCard label="ავტო-დამტკიცება" value={pct(kpi?.auto_approval_rate)} sub="rate" color="var(--blue)" />
            <KpiCard label="საშ. სანდოობა" value={pct((kpi?.avg_confidence ?? 0) * 100)} />
            <KpiCard label="ბოლო 24 სთ" value={fmt(kpi?.last_24h)} />
          </>
        )}
      </div>

      {/* P&L row */}
      <div className="dash-row">
        <div className="card dash-pnl">
          <div className="card-title">P&amp;L — მიმდინარე თვე</div>
          {pnlLoading ? <div className="dash-loading"><span className="spinner" /></div> : pnl ? (
            <div className="pnl-grid">
              <div className="pnl-item">
                <div className="pnl-label">შემოსავალი</div>
                <div className="pnl-val text-green">{fmt(pnl.income)} ₾</div>
              </div>
              <div className="pnl-item">
                <div className="pnl-label">ხარჯები</div>
                <div className="pnl-val text-red">{fmt(pnl.expenses)} ₾</div>
              </div>
              <div className="pnl-item">
                <div className="pnl-label">მოგება</div>
                <div className="pnl-val" style={{ color: (pnl.profit ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {fmt(pnl.profit)} ₾
                </div>
              </div>
              <div className="pnl-item">
                <div className="pnl-label">მარჟა</div>
                <div className="pnl-val">{pct(pnl.profit_margin)}</div>
              </div>
            </div>
          ) : <div className="text-dim">მონაცემი არ არის</div>}
        </div>

        <div className="card dash-cf">
          <div className="card-title">Cashflow — ბოლო 30 დღე</div>
          {cfLoading ? (
            <div className="dash-loading"><span className="spinner" /></div>
          ) : cfData.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={cfData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="inflow-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="outflow-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--ink-dim)' }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--ink-dim)' }} tickLine={false} axisLine={false} width={50} tickFormatter={v => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v} />
                <Tooltip
                  contentStyle={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 }}
                  formatter={(v: any) => [`${Number(v).toLocaleString()} ₾`]}
                />
                <Area type="monotone" dataKey="inflow" stroke="#10b981" fill="url(#inflow-grad)" strokeWidth={2} name="შემოსვლა" />
                <Area type="monotone" dataKey="outflow" stroke="#ef4444" fill="url(#outflow-grad)" strokeWidth={2} name="გასვლა" />
              </AreaChart>
            </ResponsiveContainer>
          ) : <div className="empty-state"><div className="empty-ic">📈</div><div className="empty-txt">მონაცემი არ არის</div></div>}
        </div>
      </div>
    </div>
  );
}
