import React, { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api/client';
import type { Draft } from '../api/types';
import './Approval.css';

const PAGE_SIZE = 20;

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending_approval: 'badge-pending',
    approved: 'badge-approved',
    auto_approved: 'badge-auto',
    rejected: 'badge-rejected',
  };
  const label: Record<string, string> = {
    pending_approval: 'Pending',
    approved: 'Approved',
    auto_approved: 'Auto',
    rejected: 'Rejected',
  };
  return <span className={`badge ${map[status] || ''}`}>{label[status] || status}</span>;
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--yellow)' : 'var(--red)';
  return (
    <div className="conf-bar" title={`${pct}%`}>
      <div className="conf-fill" style={{ width: `${pct}%`, background: color }} />
      <span className="conf-label">{pct}%</span>
    </div>
  );
}

function RejectModal({ id, onClose, onDone }: { id: string; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    await api.post(`/approval/reject/${id}`, { reason: reason || 'no reason' });
    setLoading(false);
    onDone();
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-title">უარყოფის მიზეზი</div>
        <textarea
          className="input modal-textarea"
          placeholder="მიზეზი (სურვილისამებრ)"
          value={reason}
          onChange={e => setReason(e.target.value)}
          autoFocus
        />
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>გაუქმება</button>
          <button className="btn btn-danger" onClick={submit} disabled={loading}>
            {loading ? <span className="spinner" /> : 'უარყოფა'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Approval() {
  const [tab, setTab] = useState<'pending' | 'approved' | 'rejected'>('pending');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [rejectId, setRejectId] = useState<string | null>(null);
  const qc = useQueryClient();

  const buildQueueKey = (t: string, p: number, q: string) => ['approval', 'queue', t, p, q];

  const { data, isLoading, isFetching } = useQuery({
    queryKey: buildQueueKey(tab, page, search),
    queryFn: async () => {
      const offset = (page - 1) * PAGE_SIZE;
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      if (tab !== 'pending') params.set('status', tab);
      if (search) params.set('q', search);
      const res = await api.get(`/approval/queue?${params}`);
      return res.data;
    },
    staleTime: 15000,
    refetchInterval: 30000,
  });

  const queue: Draft[] = data?.data?.queue || data?.data?.items || data?.data || [];
  const total: number = data?.data?.count ?? data?.data?.total ?? queue.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const invalidate = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['approval'] });
    qc.invalidateQueries({ queryKey: ['dashboard'] });
  }, [qc]);

  const approveMut = useMutation({
    mutationFn: (id: string) => api.post(`/approval/approve/${id}`),
    onSuccess: invalidate,
  });

  const approveAll = async () => {
    const pending = queue.filter(r => r.status === 'pending_approval');
    for (const r of pending) {
      await api.post(`/approval/approve/${r.id}`);
    }
    invalidate();
  };

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value);
    setPage(1);
  };

  return (
    <div className="page">
      {rejectId && (
        <RejectModal
          id={rejectId}
          onClose={() => setRejectId(null)}
          onDone={invalidate}
        />
      )}

      <div className="page__header">
        <div>
          <div className="page__title">Approval Queue</div>
          <div className="page__subtitle">
            სულ: {total} · {isFetching && <span className="spinner" style={{ width: 12, height: 12 }} />}
          </div>
        </div>
        {tab === 'pending' && queue.length > 0 && (
          <button className="btn btn-success" onClick={approveAll}>
            ✓ ყველას დამტკიცება ({queue.filter(r => r.status === 'pending_approval').length})
          </button>
        )}
      </div>

      {/* Tabs + Search */}
      <div className="approval-toolbar">
        <div className="tabs">
          {(['pending', 'approved', 'rejected'] as const).map(t => (
            <button
              key={t}
              className={`tab-btn${tab === t ? ' tab-btn--active' : ''}`}
              onClick={() => { setTab(t); setPage(1); }}
            >
              {t === 'pending' ? 'მოლოდინი' : t === 'approved' ? 'დამტკიცებული' : 'უარყოფილი'}
            </button>
          ))}
        </div>
        <input
          className="input approval-search"
          type="search"
          placeholder="ძიება..."
          value={search}
          onChange={handleSearch}
        />
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0 }}>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>თარიღი</th>
                <th>აღწერა</th>
                <th>თანხა</th>
                <th>ანგარიში</th>
                <th>სანდოობა</th>
                <th>სტატუსი</th>
                {tab === 'pending' && <th>მოქმედება</th>}
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: 32 }}>
                    <span className="spinner" />
                  </td>
                </tr>
              ) : queue.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-state">
                      <div className="empty-ic">ø</div>
                      <div className="empty-txt">ცარიელი რიგი</div>
                    </div>
                  </td>
                </tr>
              ) : queue.map(r => (
                <tr key={r.id}>
                  <td className="mono text-dim">{r.date || r.created_at?.slice(0, 10)}</td>
                  <td className="approval-desc">{r.description}</td>
                  <td className="num mono" style={{ fontWeight: 600 }}>
                    {Number(r.amount).toLocaleString('ka-GE', { maximumFractionDigits: 2 })} ₾
                  </td>
                  <td className="mono text-soft">{r.debit_account || r.account_code || '—'}</td>
                  <td><ConfidenceBar value={r.confidence} /></td>
                  <td>{statusBadge(r.status)}</td>
                  {tab === 'pending' && (
                    <td>
                      <div className="approval-actions">
                        <button
                          className="btn btn-success btn-sm"
                          onClick={() => approveMut.mutate(r.id)}
                          disabled={approveMut.isPending}
                        >✓</button>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => setRejectId(r.id)}
                        >✕</button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="pagination">
            <button className="btn btn-ghost btn-sm" onClick={() => setPage(p => p - 1)} disabled={page <= 1}>← წინა</button>
            <span className="pagination-info">გვ. {page} / {totalPages}</span>
            <button className="btn btn-ghost btn-sm" onClick={() => setPage(p => p + 1)} disabled={page >= totalPages}>შემდეგი →</button>
          </div>
        )}
      </div>
    </div>
  );
}
