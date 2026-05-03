import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api/client';

interface Asset {
  id: string;
  name: string;
  asset_code?: string;
  category?: string;
  purchase_price: number;
  purchase_date?: string;
  useful_life_years?: number;
  depreciation_method?: string;
  status: string;
  accumulated_depreciation?: number;
  book_value?: number;
}

function AssetModal({ asset, onClose }: { asset?: Asset; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(asset?.name || '');
  const [price, setPrice] = useState(String(asset?.purchase_price || ''));
  const [life, setLife] = useState(String(asset?.useful_life_years || '5'));
  const [method, setMethod] = useState(asset?.depreciation_method || 'straight_line');
  const [date, setDate] = useState(asset?.purchase_date || new Date().toISOString().slice(0, 10));
  const [category, setCategory] = useState(asset?.category || '');

  const mut = useMutation({
    mutationFn: (body: any) => asset
      ? api.put(`/fixed-assets/${asset.id}`, body)
      : api.post('/fixed-assets/', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['fixed-assets'] }); onClose(); },
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-title">{asset ? 'რედაქტირება' : 'ახალი აქტივი'}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {[['სახელი', name, setName], ['კატეგორია', category, setCategory]].map(([l, v, s]: any) => (
            <div key={l as string}><label style={{ display: 'block', fontSize: 11, color: 'var(--ink-dim)', marginBottom: 4 }}>{l}</label><input className="input" value={v} onChange={e => s(e.target.value)} /></div>
          ))}
          <div><label style={{ display: 'block', fontSize: 11, color: 'var(--ink-dim)', marginBottom: 4 }}>შეძენის ფასი</label><input className="input" type="number" value={price} onChange={e => setPrice(e.target.value)} /></div>
          <div><label style={{ display: 'block', fontSize: 11, color: 'var(--ink-dim)', marginBottom: 4 }}>სასარგებლო ვადა (წ.)</label><input className="input" type="number" value={life} onChange={e => setLife(e.target.value)} /></div>
          <div><label style={{ display: 'block', fontSize: 11, color: 'var(--ink-dim)', marginBottom: 4 }}>შეძენის თარიღი</label><input className="input" type="date" value={date} onChange={e => setDate(e.target.value)} /></div>
          <div>
            <label style={{ display: 'block', fontSize: 11, color: 'var(--ink-dim)', marginBottom: 4 }}>ამორტიზ. მეთოდი</label>
            <select className="input" value={method} onChange={e => setMethod(e.target.value)}>
              <option value="straight_line">Straight Line</option>
              <option value="double_declining">Double Declining</option>
              <option value="units_of_production">Units of Production</option>
            </select>
          </div>
        </div>
        <div className="modal-actions" style={{ marginTop: 16 }}>
          <button className="btn btn-ghost" onClick={onClose}>გაუქმება</button>
          <button className="btn btn-primary" onClick={() => mut.mutate({ name, category, purchase_price: +price, useful_life_years: +life, depreciation_method: method, purchase_date: date })} disabled={mut.isPending}>
            {mut.isPending ? <span className="spinner" /> : 'შენახვა'}
          </button>
        </div>
      </div>
    </div>
  );
}

function ScheduleModal({ assetId, assetName, onClose }: { assetId: string; assetName: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['fixed-assets', 'schedule', assetId],
    queryFn: () => api.get(`/fixed-assets/${assetId}/schedule`).then(r => r.data),
  });
  const rows: any[] = data?.data?.schedule || data?.schedule || [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ maxWidth: 600, width: '95%' }} onClick={e => e.stopPropagation()}>
        <div className="modal-title">ამორტიზ. გრაფიკი — {assetName}</div>
        {isLoading ? <div style={{ textAlign: 'center', padding: 24 }}><span className="spinner" /></div> : (
          <div style={{ maxHeight: 380, overflowY: 'auto' }}>
            <table className="tbl">
              <thead><tr><th>წელი</th><th>ამორტ.</th><th>დაგროვ.</th><th>საბალანსო</th></tr></thead>
              <tbody>
                {rows.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.year}</td>
                    <td className="num">₾{Number(r.depreciation || 0).toLocaleString('ka-GE', { maximumFractionDigits: 2 })}</td>
                    <td className="num">₾{Number(r.accumulated || 0).toLocaleString('ka-GE', { maximumFractionDigits: 2 })}</td>
                    <td className="num" style={{ fontWeight: 700 }}>₾{Number(r.book_value || 0).toLocaleString('ka-GE', { maximumFractionDigits: 2 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="modal-actions" style={{ marginTop: 12 }}>
          <button className="btn btn-ghost" onClick={onClose}>დახურვა</button>
        </div>
      </div>
    </div>
  );
}

export default function FixedAssets() {
  const [status, setStatus] = useState('active');
  const [modal, setModal] = useState<{ open: boolean; asset?: Asset }>({ open: false });
  const [schedule, setSchedule] = useState<{ id: string; name: string } | null>(null);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['fixed-assets', status],
    queryFn: () => api.get(`/fixed-assets/?status=${status}`).then(r => r.data),
    staleTime: 60000,
  });
  const assets: Asset[] = data?.data?.assets || data?.assets || data?.data || [];

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/fixed-assets/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fixed-assets'] }),
  });

  const totalCost = assets.reduce((s, a) => s + Number(a.purchase_price || 0), 0);
  const totalBook = assets.reduce((s, a) => s + Number(a.book_value || a.purchase_price || 0), 0);

  return (
    <div className="page">
      {modal.open && <AssetModal asset={modal.asset} onClose={() => setModal({ open: false })} />}
      {schedule && <ScheduleModal assetId={schedule.id} assetName={schedule.name} onClose={() => setSchedule(null)} />}
      <div className="page__header">
        <div>
          <div className="page__title">Fixed Assets</div>
          <div className="page__subtitle">სულ: ₾{totalCost.toLocaleString('ka-GE', { maximumFractionDigits: 0 })} · საბალ.: ₾{totalBook.toLocaleString('ka-GE', { maximumFractionDigits: 0 })}</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <select className="input" value={status} onChange={e => setStatus(e.target.value)} style={{ width: 140 }}>
            <option value="active">აქტიური</option>
            <option value="disposed">ჩამოწერილი</option>
            <option value="">ყველა</option>
          </select>
          <button className="btn btn-primary" onClick={() => setModal({ open: true })}>+ ახალი</button>
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>სახელი</th><th>კატ.</th><th>შეძ. ფასი</th><th>ვადა (წ.)</th><th>მეთოდი</th><th>საბ. ღირ.</th><th>სტ.</th><th></th></tr></thead>
            <tbody>
              {isLoading ? <tr><td colSpan={8} style={{ textAlign: 'center', padding: 32 }}><span className="spinner" /></td></tr>
                : assets.length === 0 ? <tr><td colSpan={8}><div className="empty-state"><div className="empty-ic">🏗</div><div className="empty-txt">აქტივი არ არის</div></div></td></tr>
                : assets.map(a => (
                  <tr key={a.id}>
                    <td style={{ fontWeight: 600 }}>{a.name}</td>
                    <td className="text-dim">{a.category || '—'}</td>
                    <td className="num">₾{Number(a.purchase_price).toLocaleString('ka-GE', { maximumFractionDigits: 0 })}</td>
                    <td className="num">{a.useful_life_years || '—'}</td>
                    <td className="text-dim" style={{ fontSize: 12 }}>{a.depreciation_method?.replace('_', ' ')}</td>
                    <td className="num" style={{ fontWeight: 700 }}>₾{Number(a.book_value || a.purchase_price).toLocaleString('ka-GE', { maximumFractionDigits: 0 })}</td>
                    <td><span className={`badge ${a.status === 'active' ? 'badge-approved' : 'badge-rejected'}`}>{a.status}</span></td>
                    <td>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="btn btn-ghost btn-sm" onClick={() => setSchedule({ id: a.id, name: a.name })} title="გრაფიკი">📅</button>
                        <button className="btn btn-ghost btn-sm" onClick={() => setModal({ open: true, asset: a })}>✏️</button>
                        <button className="btn btn-danger btn-sm" onClick={() => { if (window.confirm('წაშლა?')) deleteMut.mutate(a.id); }}>🗑</button>
                      </div>
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
