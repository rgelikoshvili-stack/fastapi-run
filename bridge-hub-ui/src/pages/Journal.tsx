import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import api from '../api/client';
import './Journal.css';

const PAGE = 50;

interface JournalEntry {
  id: string;
  date: string;
  description: string;
  amount: number;
  debit_account?: string;
  credit_account?: string;
  account_code?: string;
  partner?: string;
  counterparty_name?: string;
  status?: string;
  source_type?: string;
}

function EntryRow({ entry, onCorrect }: { entry: JournalEntry; onCorrect: (e: JournalEntry) => void }) {
  const [open, setOpen] = useState(false);
  const dr = entry.debit_account || entry.account_code || '—';
  const cr = entry.credit_account || '—';
  const partner = entry.partner || entry.counterparty_name || '';

  return (
    <div className="j-card">
      <div className="j-card-head" onClick={() => setOpen(o => !o)}>
        <div className="j-date mono text-dim">{entry.date || '—'}</div>
        <div className="j-meta">
          <div className="j-desc">{entry.description || '—'}</div>
          <div className="j-tags">
            <span className="j-tag">Dr <b>{dr}</b></span>
            <span className="j-tag">Cr <b>{cr}</b></span>
            {partner && <span className="j-tag">კომ. <b>{partner.slice(0, 25)}{partner.length > 25 ? '…' : ''}</b></span>}
          </div>
        </div>
        <div className="j-amount num">{Number(entry.amount).toLocaleString('ka-GE', { maximumFractionDigits: 2 })} ₾</div>
        <div className="j-actions" onClick={e => e.stopPropagation()}>
          <button className="btn btn-ghost btn-sm" onClick={() => setOpen(o => !o)}>👁</button>
          <button className="btn btn-ghost btn-sm" onClick={() => onCorrect(entry)}>✏️</button>
        </div>
      </div>
      {open && (
        <div className="j-detail">
          <div className="j-detail-grid">
            <div><span className="j-dl">ID</span><span className="mono text-dim">{entry.id}</span></div>
            <div><span className="j-dl">სტატუსი</span><span>{entry.status || '—'}</span></div>
            <div><span className="j-dl">წყარო</span><span>{entry.source_type || '—'}</span></div>
            <div><span className="j-dl">Debit</span><span className="mono">{dr}</span></div>
            <div><span className="j-dl">Credit</span><span className="mono">{cr}</span></div>
            {partner && <div><span className="j-dl">კონტრაჰენტი</span><span>{partner}</span></div>}
          </div>
        </div>
      )}
    </div>
  );
}

function CorrectionModal({ entry, onClose }: { entry: JournalEntry; onClose: () => void }) {
  const [debit, setDebit] = useState(entry.debit_account || '');
  const [credit, setCredit] = useState(entry.credit_account || '');
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async () => {
    setLoading(true);
    await api.post(`/approval/correct/${entry.id}`, { debit_account: debit, credit_account: credit, reason });
    setLoading(false);
    setDone(true);
    setTimeout(onClose, 1000);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-title">კორექტირება — {entry.description?.slice(0, 40)}</div>
        {done ? (
          <div style={{ color: 'var(--green)', textAlign: 'center', padding: 16 }}>✓ შენახულია</div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ fontSize: 11, color: 'var(--ink-dim)', display: 'block', marginBottom: 4 }}>DEBIT</label>
                <input className="input" value={debit} onChange={e => setDebit(e.target.value)} placeholder="1110" />
              </div>
              <div>
                <label style={{ fontSize: 11, color: 'var(--ink-dim)', display: 'block', marginBottom: 4 }}>CREDIT</label>
                <input className="input" value={credit} onChange={e => setCredit(e.target.value)} placeholder="3110" />
              </div>
            </div>
            <textarea className="input" style={{ height: 72, resize: 'vertical', marginTop: 8 }}
              placeholder="მიზეზი (სურვილისამებრ)" value={reason} onChange={e => setReason(e.target.value)} />
            <div className="modal-actions" style={{ marginTop: 12 }}>
              <button className="btn btn-ghost" onClick={onClose}>გაუქმება</button>
              <button className="btn btn-primary" onClick={submit} disabled={loading}>
                {loading ? <span className="spinner" /> : 'შენახვა'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function Journal() {
  const [date, setDate] = useState('');
  const [offset, setOffset] = useState(0);
  const [correcting, setCorrecting] = useState<JournalEntry | null>(null);
  const [queryDate, setQueryDate] = useState('');

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['journal', queryDate, offset],
    queryFn: () => {
      const p = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
      if (queryDate) p.set('date', queryDate);
      return api.get(`/reports/journal?${p}`).then(r => r.data);
    },
    staleTime: 30000,
  });

  const items: JournalEntry[] = data?.items || [];
  const total: number = data?.total || 0;
  const totalPages = Math.ceil(total / PAGE);
  const curPage = Math.floor(offset / PAGE) + 1;

  const run = () => { setQueryDate(date); setOffset(0); };

  return (
    <div className="page">
      {correcting && <CorrectionModal entry={correcting} onClose={() => setCorrecting(null)} />}
      <div className="page__header">
        <div>
          <div className="page__title">Journal</div>
          <div className="page__subtitle">სულ: {total} ჩანაწერი</div>
        </div>
      </div>

      <div className="journal-toolbar">
        <input className="input" type="date" value={date} onChange={e => setDate(e.target.value)} style={{ width: 160 }} />
        <button className="btn btn-primary" onClick={run} disabled={isFetching}>
          {isFetching ? <span className="spinner" /> : 'ჩვენება'}
        </button>
        {queryDate && (
          <button className="btn btn-ghost" onClick={() => { setDate(''); setQueryDate(''); setOffset(0); }}>
            ×  ფილტრის გასუფთავება
          </button>
        )}
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><span className="spinner" /></div>
      ) : items.length === 0 ? (
        <div className="empty-state"><div className="empty-ic">📒</div><div className="empty-txt">ჩანაწერები არ მოიძებნა</div></div>
      ) : (
        <div className="j-list">
          {items.map(e => <EntryRow key={e.id} entry={e} onCorrect={setCorrecting} />)}
        </div>
      )}

      {totalPages > 1 && (
        <div className="pagination">
          <button className="btn btn-ghost btn-sm" onClick={() => setOffset(o => Math.max(0, o - PAGE))} disabled={offset === 0}>← წინა</button>
          <span className="pagination-info">გვ. {curPage} / {totalPages} ({total})</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setOffset(o => o + PAGE)} disabled={curPage >= totalPages}>შემდეგი →</button>
        </div>
      )}
    </div>
  );
}
