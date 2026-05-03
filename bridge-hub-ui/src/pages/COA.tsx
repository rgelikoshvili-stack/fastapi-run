import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

interface Account {
  code: string;
  name_ka?: string;
  name_en?: string;
  category?: string;
  is_active?: boolean;
}

export default function COA() {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');

  const { data: listData, isLoading } = useQuery({
    queryKey: ['coa', 'list', category],
    queryFn: () => api.get(`/coa/list${category ? `?category=${category}` : ''}`).then(r => r.data),
    staleTime: 300000,
  });
  const allAccounts: Account[] = listData?.accounts || listData?.data?.accounts || [];

  const { data: catData } = useQuery({
    queryKey: ['coa', 'categories'],
    queryFn: () => api.get('/coa/categories').then(r => r.data),
    staleTime: 300000,
  });
  const categories: string[] = (catData?.categories || []).map((c: any) => c.category || c);

  const filtered = search
    ? allAccounts.filter(a =>
        a.code.includes(search) ||
        a.name_ka?.toLowerCase().includes(search.toLowerCase()) ||
        a.name_en?.toLowerCase().includes(search.toLowerCase()))
    : allAccounts;

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <div className="page__title">Chart of Accounts</div>
          <div className="page__subtitle">სულ: {allAccounts.length} ანგარიში</div>
        </div>
      </div>

      <div className="approval-toolbar">
        <input className="input" type="search" placeholder="კოდი ან სახელი..." value={search} onChange={e => setSearch(e.target.value)} style={{ width: 240 }} />
        <select className="input" value={category} onChange={e => setCategory(e.target.value)} style={{ width: 160 }}>
          <option value="">ყველა კატ.</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>კოდი</th><th>სახელი (KA)</th><th>სახელი (EN)</th><th>კატეგ.</th></tr></thead>
            <tbody>
              {isLoading ? <tr><td colSpan={4} style={{ textAlign: 'center', padding: 32 }}><span className="spinner" /></td></tr>
                : filtered.length === 0 ? <tr><td colSpan={4}><div className="empty-state"><div className="empty-ic">🗂</div><div className="empty-txt">ანგარიში არ მოიძებნა</div></div></td></tr>
                : filtered.map(a => (
                  <tr key={a.code}>
                    <td className="mono" style={{ fontWeight: 700, color: 'var(--accent)' }}>{a.code}</td>
                    <td>{a.name_ka || '—'}</td>
                    <td className="text-soft">{a.name_en || '—'}</td>
                    <td><span className="badge badge-auto">{a.category || '—'}</span></td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
