import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api/client';
import './Inventory.css';

interface Item {
  id: string;
  name: string;
  sku?: string;
  category?: string;
  quantity: number;
  unit_cost: number;
  reorder_point?: number;
  unit?: string;
}

function ItemModal({ item, onClose }: { item?: Item; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(item?.name || '');
  const [sku, setSku] = useState(item?.sku || '');
  const [qty, setQty] = useState(String(item?.quantity || 0));
  const [cost, setCost] = useState(String(item?.unit_cost || 0));
  const [reorder, setReorder] = useState(String(item?.reorder_point || 0));
  const [unit, setUnit] = useState(item?.unit || 'ცალი');

  const mut = useMutation({
    mutationFn: (body: any) => item
      ? api.put(`/inventory/items/${item.id}`, body)
      : api.post('/inventory/items/create', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['inventory'] }); onClose(); },
  });

  const submit = () => mut.mutate({ name, sku, quantity: +qty, unit_cost: +cost, reorder_point: +reorder, unit });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-title">{item ? 'რედაქტირება' : 'ახალი პროდუქტი'}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div><label className="inv-label">სახელი</label><input className="input" value={name} onChange={e => setName(e.target.value)} /></div>
          <div><label className="inv-label">SKU</label><input className="input" value={sku} onChange={e => setSku(e.target.value)} /></div>
          <div><label className="inv-label">რაოდენობა</label><input className="input" type="number" value={qty} onChange={e => setQty(e.target.value)} /></div>
          <div><label className="inv-label">ერთეულის ღირებულება</label><input className="input" type="number" value={cost} onChange={e => setCost(e.target.value)} /></div>
          <div><label className="inv-label">Reorder Point</label><input className="input" type="number" value={reorder} onChange={e => setReorder(e.target.value)} /></div>
          <div><label className="inv-label">ერთეული</label><input className="input" value={unit} onChange={e => setUnit(e.target.value)} /></div>
        </div>
        <div className="modal-actions" style={{ marginTop: 16 }}>
          <button className="btn btn-ghost" onClick={onClose}>გაუქმება</button>
          <button className="btn btn-primary" onClick={submit} disabled={mut.isPending}>
            {mut.isPending ? <span className="spinner" /> : 'შენახვა'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Inventory() {
  const [tab, setTab] = useState<'items' | 'movements' | 'valuation'>('items');
  const [search, setSearch] = useState('');
  const [lowStock, setLowStock] = useState(false);
  const [modal, setModal] = useState<{ open: boolean; item?: Item }>({ open: false });
  const [valMethod, setValMethod] = useState('average');
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['inventory', 'items', search, lowStock],
    queryFn: () => api.get(`/inventory/items?search=${encodeURIComponent(search)}&low_stock=${lowStock}&limit=100&offset=0`).then(r => r.data),
    staleTime: 30000,
  });
  const items: Item[] = data?.data?.items || data?.items || data?.data || [];

  const { data: movData } = useQuery({
    queryKey: ['inventory', 'movements'],
    queryFn: () => api.get('/inventory/movements?limit=50&offset=0').then(r => r.data),
    enabled: tab === 'movements',
    staleTime: 30000,
  });
  const movements: any[] = movData?.data?.movements || movData?.movements || movData?.data || [];

  const { data: valData, refetch: refetchVal, isFetching: valFetching } = useQuery({
    queryKey: ['inventory', 'valuation', valMethod],
    queryFn: () => api.get(`/inventory/valuation?method=${valMethod}`).then(r => r.data),
    enabled: tab === 'valuation',
    staleTime: 60000,
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/inventory/items/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory', 'items'] }),
  });

  return (
    <div className="page">
      {modal.open && <ItemModal item={modal.item} onClose={() => setModal({ open: false })} />}
      <div className="page__header">
        <div>
          <div className="page__title">Inventory</div>
          <div className="page__subtitle">FIFO / LIFO / საშ. ღირებულება</div>
        </div>
        {tab === 'items' && (
          <button className="btn btn-primary" onClick={() => setModal({ open: true })}>+ ახალი</button>
        )}
      </div>

      <div className="approval-toolbar">
        <div className="tabs">
          <button className={`tab-btn${tab === 'items' ? ' tab-btn--active' : ''}`} onClick={() => setTab('items')}>📦 პროდუქტები</button>
          <button className={`tab-btn${tab === 'movements' ? ' tab-btn--active' : ''}`} onClick={() => setTab('movements')}>🔄 მოძრაობები</button>
          <button className={`tab-btn${tab === 'valuation' ? ' tab-btn--active' : ''}`} onClick={() => setTab('valuation')}>💰 შეფასება</button>
        </div>
        {tab === 'items' && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input className="input" type="search" placeholder="ძიება..." value={search} onChange={e => setSearch(e.target.value)} style={{ width: 200 }} />
            <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, color: 'var(--ink-soft)', cursor: 'pointer', whiteSpace: 'nowrap' }}>
              <input type="checkbox" checked={lowStock} onChange={e => setLowStock(e.target.checked)} />
              Low stock
            </label>
          </div>
        )}
      </div>

      {tab === 'items' && (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>სახელი</th><th>SKU</th><th>რაოდ.</th><th>ღირ./ცალ.</th><th>სულ ღირ.</th><th>Reorder</th><th></th></tr></thead>
              <tbody>
                {isLoading ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: 32 }}><span className="spinner" /></td></tr>
                  : items.length === 0 ? <tr><td colSpan={7}><div className="empty-state"><div className="empty-ic">📦</div><div className="empty-txt">პროდუქტი არ არის</div></div></td></tr>
                  : items.map(it => (
                    <tr key={it.id}>
                      <td style={{ fontWeight: 600 }}>{it.name}</td>
                      <td className="mono text-dim">{it.sku || '—'}</td>
                      <td className={`num${it.reorder_point && it.quantity <= it.reorder_point ? ' text-red' : ''}`}>{it.quantity} {it.unit || ''}</td>
                      <td className="num">₾{Number(it.unit_cost).toLocaleString('ka-GE', { maximumFractionDigits: 2 })}</td>
                      <td className="num" style={{ fontWeight: 600 }}>₾{(it.quantity * it.unit_cost).toLocaleString('ka-GE', { maximumFractionDigits: 0 })}</td>
                      <td className="num text-dim">{it.reorder_point || '—'}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button className="btn btn-ghost btn-sm" onClick={() => setModal({ open: true, item: it })}>✏️</button>
                          <button className="btn btn-danger btn-sm" onClick={() => { if (window.confirm('წაშლა?')) deleteMut.mutate(it.id); }}>🗑</button>
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'movements' && (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>თარიღი</th><th>პროდუქტი</th><th>ტიპი</th><th>რაოდ.</th><th>ეkon</th></tr></thead>
              <tbody>
                {movements.length === 0 ? <tr><td colSpan={5}><div className="empty-state"><div className="empty-ic">🔄</div><div className="empty-txt">მოძრაობა არ არის</div></div></td></tr>
                  : movements.map((m: any, i: number) => (
                    <tr key={i}>
                      <td className="mono text-dim">{m.created_at?.slice(0, 10)}</td>
                      <td>{m.item_name || m.item_id}</td>
                      <td><span className={`badge ${m.movement_type === 'in' ? 'badge-approved' : 'badge-rejected'}`}>{m.movement_type}</span></td>
                      <td className="num">{m.quantity}</td>
                      <td className="num">₾{Number(m.unit_cost || 0).toLocaleString('ka-GE', { maximumFractionDigits: 2 })}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'valuation' && (
        <div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            {['fifo', 'lifo', 'average'].map(m => (
              <button key={m} className={`btn ${valMethod === m ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setValMethod(m)}>
                {m.toUpperCase()}
              </button>
            ))}
            <button className="btn btn-ghost" onClick={() => refetchVal()} disabled={valFetching}>
              {valFetching ? <span className="spinner" /> : '↻ განახლება'}
            </button>
          </div>
          {valData && (
            <div className="card" style={{ padding: 0 }}>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th>პროდუქტი</th><th>SKU</th><th>რაოდ.</th><th>ღირ./ცალ.</th><th>სულ</th></tr></thead>
                  <tbody>
                    {(valData?.data?.items || valData?.items || []).map((it: any, i: number) => (
                      <tr key={i}>
                        <td>{it.name}</td>
                        <td className="mono text-dim">{it.sku || '—'}</td>
                        <td className="num">{it.quantity}</td>
                        <td className="num">₾{Number(it.unit_cost || it.avg_cost || 0).toLocaleString('ka-GE', { maximumFractionDigits: 2 })}</td>
                        <td className="num" style={{ fontWeight: 700 }}>₾{Number(it.total_value || 0).toLocaleString('ka-GE', { maximumFractionDigits: 0 })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
