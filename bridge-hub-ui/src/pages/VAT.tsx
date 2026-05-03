import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

function fmt(n: number) { return Number(n || 0).toLocaleString('ka-GE', { maximumFractionDigits: 2 }); }

type Tab = 'vat' | 'salary' | 'corporate' | 'rates';

function VATCalc() {
  const [amount, setAmount] = useState('1000');
  const [inclusive, setInclusive] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const calc = async () => {
    setLoading(true);
    const res = await api.post('/tax/vat', { amount: +amount, vat_inclusive: inclusive }).catch(() => null);
    setResult(res?.data?.data || res?.data);
    setLoading(false);
  };

  return (
    <div className="card" style={{ maxWidth: 400 }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>VAT კალკულატორი (18%)</div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <input className="input" type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder="თანხა" />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', whiteSpace: 'nowrap' }}>
          <input type="checkbox" checked={inclusive} onChange={e => setInclusive(e.target.checked)} />
          VAT ჩათვლით
        </label>
      </div>
      <button className="btn btn-primary" onClick={calc} disabled={loading} style={{ width: '100%' }}>
        {loading ? <span className="spinner" /> : 'გამოთვლა'}
      </button>
      {result && (
        <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
          {[['Net', result.net_amount ?? result.base], ['VAT (18%)', result.vat_amount ?? result.vat], ['Gross', result.gross_amount ?? result.total]].map(([l, v]: any) => (
            <div key={l as string} style={{ padding: '8px 12px', background: 'var(--bg)', borderRadius: 6 }}>
              <div style={{ fontSize: 10, color: 'var(--ink-dim)', textTransform: 'uppercase' }}>{l}</div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>₾{fmt(v ?? 0)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SalaryCalc() {
  const [gross, setGross] = useState('3000');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const calc = async () => {
    setLoading(true);
    const res = await api.post('/tax/salary', { gross_salary: +gross }).catch(() => null);
    setResult(res?.data?.data || res?.data);
    setLoading(false);
  };

  return (
    <div className="card" style={{ maxWidth: 400 }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>ხელფასის გადასახადი</div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <input className="input" type="number" value={gross} onChange={e => setGross(e.target.value)} placeholder="ბრუტო" />
        <button className="btn btn-primary" onClick={calc} disabled={loading}>
          {loading ? <span className="spinner" /> : 'გამოთვლა'}
        </button>
      </div>
      {result && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
          {[['ბრუტო', result.gross_salary], ['PIT (20%)', result.pit], ['PAYG (2%)', result.pension_employee], ['ბ/ჟ (2%)', result.pension_employer], ['ნეტო', result.net_salary]].map(([l, v]: any) => (
            <div key={l as string} style={{ padding: '8px 12px', background: 'var(--bg)', borderRadius: 6 }}>
              <div style={{ fontSize: 10, color: 'var(--ink-dim)', textTransform: 'uppercase' }}>{l}</div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>₾{fmt(v ?? 0)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CorporateTax() {
  const [profit, setProfit] = useState('10000');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const calc = async () => {
    setLoading(true);
    const res = await api.post('/tax/corporate', { distributed_profit: +profit }).catch(() => null);
    setResult(res?.data?.data || res?.data);
    setLoading(false);
  };

  return (
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
      <div className="card" style={{ flex: '0 0 360px' }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>კორპ. გადასახადი (CIT 15%)</div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <input className="input" type="number" value={profit} onChange={e => setProfit(e.target.value)} placeholder="გადანაწ. მოგება" />
          <button className="btn btn-primary" onClick={calc} disabled={loading}>
            {loading ? <span className="spinner" /> : 'გამოთვლა'}
          </button>
        </div>
        {result && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
            {[['Tax Base', result.tax_base], ['CIT (15%)', result.cit], ['Net', result.net]].map(([l, v]: any) => (
              <div key={l as string} style={{ padding: '8px 12px', background: 'var(--bg)', borderRadius: 6 }}>
                <div style={{ fontSize: 10, color: 'var(--ink-dim)', textTransform: 'uppercase' }}>{l}</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>₾{fmt(v ?? 0)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TaxRates() {
  const { data, isLoading } = useQuery({
    queryKey: ['tax', 'rates'],
    queryFn: () => api.get('/tax/rates').then(r => r.data),
    staleTime: 3600000,
  });
  const rates: any = data?.data || data || {};

  return (
    <div className="card" style={{ maxWidth: 500 }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>საგადასახადო განაკვეთები</div>
      {isLoading ? <span className="spinner" /> : (
        <table className="tbl">
          <thead><tr><th>გადასახადი</th><th>განაკვეთი</th></tr></thead>
          <tbody>
            {Object.entries(rates).map(([k, v]: [string, any]) => (
              <tr key={k}>
                <td style={{ textTransform: 'uppercase', fontSize: 12 }}>{k.replace(/_/g, ' ')}</td>
                <td className="num" style={{ fontWeight: 700 }}>{typeof v === 'number' ? `${(v * 100).toFixed(0)}%` : String(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function VAT() {
  const [tab, setTab] = useState<Tab>('vat');

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">VAT & Tax</div>
      </div>
      <div className="approval-toolbar">
        <div className="tabs">
          <button className={`tab-btn${tab === 'vat' ? ' tab-btn--active' : ''}`} onClick={() => setTab('vat')}>VAT</button>
          <button className={`tab-btn${tab === 'salary' ? ' tab-btn--active' : ''}`} onClick={() => setTab('salary')}>ხელფასი</button>
          <button className={`tab-btn${tab === 'corporate' ? ' tab-btn--active' : ''}`} onClick={() => setTab('corporate')}>CIT</button>
          <button className={`tab-btn${tab === 'rates' ? ' tab-btn--active' : ''}`} onClick={() => setTab('rates')}>განაკვეთები</button>
        </div>
      </div>
      {tab === 'vat' && <VATCalc />}
      {tab === 'salary' && <SalaryCalc />}
      {tab === 'corporate' && <CorporateTax />}
      {tab === 'rates' && <TaxRates />}
    </div>
  );
}
