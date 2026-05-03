import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api/client';
import './Documents.css';

interface Doc {
  id: string;
  file_name: string;
  doc_type: string;
  status: string;
  uploaded_at: string;
  processing_status?: string;
}

interface EmailMsg {
  message_id: string;
  subject: string;
  sender: string;
  date: string;
  attachments?: string[];
}

function UploadZone({ onUpload }: { onUpload: (file: File, type: string) => void }) {
  const [dragging, setDragging] = useState(false);
  const [type, setType] = useState('invoice');
  const inputRef = useRef<HTMLInputElement>(null);

  const handle = (file: File) => onUpload(file, type);

  return (
    <div className="card upload-zone-card">
      <div className="upload-toolbar">
        <select className="input" value={type} onChange={e => setType(e.target.value)} style={{ width: 160 }}>
          <option value="invoice">ინვოისი</option>
          <option value="expense">ხარჯი</option>
          <option value="contract">კონტრაქტი</option>
          <option value="bank_statement">საბანკო ამონაწერი</option>
          <option value="other">სხვა</option>
        </select>
      </div>
      <div
        className={`upload-zone${dragging ? ' upload-zone--drag' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handle(f); }}
        onClick={() => inputRef.current?.click()}
      >
        <input ref={inputRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.heic" style={{ display: 'none' }}
          onChange={e => { const f = e.target.files?.[0]; if (f) handle(f); }} />
        <div className="upload-icon">📄</div>
        <div className="upload-text">ჩააგდეთ ფაილი ან დააჭირეთ ატვირთვისთვის</div>
        <div className="upload-sub">PDF, PNG, JPG, HEIC</div>
      </div>
    </div>
  );
}

function StatusBadge({ s }: { s: string }) {
  const map: Record<string, string> = {
    pending: 'badge-pending', processed: 'badge-approved',
    failed: 'badge-rejected', processing: 'badge-auto',
  };
  return <span className={`badge ${map[s] || ''}`}>{s}</span>;
}

export default function Documents() {
  const [tab, setTab] = useState<'docs' | 'email'>('docs');
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState('');
  const qc = useQueryClient();

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: () => api.get('/documents?limit=100').then(r => r.data),
    staleTime: 30000,
  });
  const docs: Doc[] = docsData?.data?.documents || docsData?.documents || docsData?.data || [];

  const { data: emailData, isLoading: emailLoading } = useQuery({
    queryKey: ['email-inbox'],
    queryFn: () => api.get('/email-invoice/inbox').then(r => r.data),
    enabled: tab === 'email',
    staleTime: 60000,
  });
  const emails: EmailMsg[] = emailData?.data?.messages || emailData?.messages || [];

  const uploadMut = useMutation({
    mutationFn: async ({ file, type }: { file: File; type: string }) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('doc_type', type);
      return api.post('/documents/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
    },
    onSuccess: () => { setMsg('✓ ატვირთულია — AI ამუშავებს'); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: () => setMsg('✕ ატვირთვა ვერ მოხერხდა'),
  });

  const ocrMut = useMutation({
    mutationFn: ({ file, type }: { file: File; type: string }) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('doc_type', type);
      return api.post('/ocr/extract-and-draft', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
    },
    onSuccess: () => { setMsg('✓ OCR + Draft შეიქმნა'); qc.invalidateQueries({ queryKey: ['documents'] }); },
    onError: () => setMsg('✕ OCR შეცდომა'),
  });

  const handleUpload = (file: File, type: string) => {
    setMsg('');
    uploadMut.mutate({ file, type });
  };

  const handleOcr = (file: File, type: string) => {
    setMsg('');
    ocrMut.mutate({ file, type });
  };

  const confirmEmail = async (mid: string, fn: string) => {
    await api.post('/email-invoice/confirm-process', { message_id: mid, attachment: fn });
    qc.invalidateQueries({ queryKey: ['email-inbox'] });
    setMsg('✓ Email invoice დამუშავდა');
  };

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <div className="page__title">Documents</div>
          <div className="page__subtitle">ფაილების ატვირთვა + OCR + Email Invoice</div>
        </div>
        {msg && <div style={{ color: msg.startsWith('✓') ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>{msg}</div>}
      </div>

      {/* Upload zones */}
      <div className="docs-upload-row">
        <div>
          <div className="docs-upload-label">ატვირთვა (სია-ში)</div>
          <UploadZone onUpload={handleUpload} />
        </div>
        <div>
          <div className="docs-upload-label">OCR + Draft შექმნა</div>
          <UploadZone onUpload={handleOcr} />
        </div>
      </div>

      {/* Tabs */}
      <div className="approval-toolbar" style={{ marginTop: 16 }}>
        <div className="tabs">
          <button className={`tab-btn${tab === 'docs' ? ' tab-btn--active' : ''}`} onClick={() => setTab('docs')}>
            📄 ატვირთული ({docs.length})
          </button>
          <button className={`tab-btn${tab === 'email' ? ' tab-btn--active' : ''}`} onClick={() => setTab('email')}>
            📧 Email Inbox
          </button>
        </div>
      </div>

      {tab === 'docs' && (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr><th>ფაილი</th><th>ტიპი</th><th>სტატუსი</th><th>ატვირთვა</th></tr>
              </thead>
              <tbody>
                {docsLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', padding: 32 }}><span className="spinner" /></td></tr>
                ) : docs.length === 0 ? (
                  <tr><td colSpan={4}><div className="empty-state"><div className="empty-ic">📁</div><div className="empty-txt">დოკუმენტი არ არის</div></div></td></tr>
                ) : docs.map(d => (
                  <tr key={d.id}>
                    <td className="text-soft" style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.file_name}</td>
                    <td><span className="badge badge-auto">{d.doc_type}</span></td>
                    <td><StatusBadge s={d.processing_status || d.status} /></td>
                    <td className="mono text-dim" style={{ fontSize: 12 }}>{d.uploaded_at?.slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'email' && (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr><th>თემა</th><th>გამგზავნი</th><th>თარიღი</th><th>ატაჩმენტი</th><th></th></tr>
              </thead>
              <tbody>
                {emailLoading ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', padding: 32 }}><span className="spinner" /></td></tr>
                ) : emails.length === 0 ? (
                  <tr><td colSpan={5}><div className="empty-state"><div className="empty-ic">📧</div><div className="empty-txt">Email-ები არ არის</div></div></td></tr>
                ) : emails.map(m => (
                  <tr key={m.message_id}>
                    <td style={{ maxWidth: 220 }}>{m.subject}</td>
                    <td className="text-dim" style={{ fontSize: 12 }}>{m.sender}</td>
                    <td className="mono text-dim" style={{ fontSize: 12 }}>{m.date?.slice(0, 10)}</td>
                    <td>{(m.attachments || []).map(fn => (
                      <span key={fn} className="badge badge-auto" style={{ marginRight: 4 }}>{fn}</span>
                    ))}</td>
                    <td>
                      {(m.attachments || []).map(fn => (
                        <button key={fn} className="btn btn-success btn-sm" onClick={() => confirmEmail(m.message_id, fn)}>
                          ✓ Draft
                        </button>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
