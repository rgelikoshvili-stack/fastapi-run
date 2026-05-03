import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api/client';

interface Employee {
  id: string;
  name: string;
  position?: string;
  department?: string;
  salary: number;
  status: string;
  hire_date?: string;
  email?: string;
}

function EmployeeModal({ emp, onClose }: { emp?: Employee; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(emp?.name || '');
  const [position, setPosition] = useState(emp?.position || '');
  const [dept, setDept] = useState(emp?.department || '');
  const [salary, setSalary] = useState(String(emp?.salary || ''));
  const [email, setEmail] = useState(emp?.email || '');

  const mut = useMutation({
    mutationFn: (body: any) => emp
      ? api.put(`/employees/${emp.id}`, body)
      : api.post('/employees', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['employees'] }); onClose(); },
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-title">{emp ? 'თანამშრომლის რედაქტირება' : 'ახალი თანამშრომელი'}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {[['სახელი', name, setName, 'text'], ['ელ-ფოსტა', email, setEmail, 'email'],
            ['პოზიცია', position, setPosition, 'text'], ['დეპარტამენტი', dept, setDept, 'text'],
            ['ხელფასი', salary, setSalary, 'number']].map(([label, val, setter, type]: any) => (
            <div key={label as string}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--ink-dim)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.06em' }}>{label}</label>
              <input className="input" type={type} value={val} onChange={e => setter(e.target.value)} />
            </div>
          ))}
        </div>
        <div className="modal-actions" style={{ marginTop: 16 }}>
          <button className="btn btn-ghost" onClick={onClose}>გაუქმება</button>
          <button className="btn btn-primary" onClick={() => mut.mutate({ name, position, department: dept, salary: +salary, email })} disabled={mut.isPending}>
            {mut.isPending ? <span className="spinner" /> : 'შენახვა'}
          </button>
        </div>
      </div>
    </div>
  );
}

function PayrollCalc() {
  const [gross, setGross] = useState('3000');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const calc = async () => {
    setLoading(true);
    const res = await api.post('/payroll/calculate', { gross_salary: +gross }).catch(() => null);
    setResult(res?.data?.data || res?.data);
    setLoading(false);
  };

  return (
    <div className="card" style={{ maxWidth: 420 }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>გადასახადის კალკულატორი</div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <input className="input" type="number" value={gross} onChange={e => setGross(e.target.value)} placeholder="ბრუტო ხელფასი" />
        <button className="btn btn-primary" onClick={calc} disabled={loading}>
          {loading ? <span className="spinner" /> : 'გამოთვლა'}
        </button>
      </div>
      {result && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
          {[['ბრუტო', result.gross_salary], ['PIT (20%)', result.pit], ['PAYG (2%)', result.pension_employee],
            ['დამსაქმებლის ნაწილი', result.pension_employer], ['ნეტო', result.net_salary]
          ].map(([l, v]: any) => (
            <div key={l} style={{ padding: '8px 12px', background: 'var(--bg)', borderRadius: 6 }}>
              <div style={{ fontSize: 10, color: 'var(--ink-dim)', textTransform: 'uppercase', letterSpacing: '.05em' }}>{l}</div>
              <div style={{ fontSize: 16, fontWeight: 700, marginTop: 2 }}>₾{Number(v || 0).toLocaleString('ka-GE', { maximumFractionDigits: 2 })}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Payroll() {
  const [tab, setTab] = useState<'employees' | 'calc'>('employees');
  const [status, setStatus] = useState('active');
  const [modal, setModal] = useState<{ open: boolean; emp?: Employee }>({ open: false });
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['employees', status],
    queryFn: () => api.get(`/employees?status=${status}&limit=200`).then(r => r.data),
    staleTime: 60000,
  });
  const employees: Employee[] = data?.data?.employees || data?.employees || data?.data || [];

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/employees/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['employees'] }),
  });

  return (
    <div className="page">
      {modal.open && <EmployeeModal emp={modal.emp} onClose={() => setModal({ open: false })} />}
      <div className="page__header">
        <div>
          <div className="page__title">Payroll</div>
          <div className="page__subtitle">თანამშრომლები + გადასახადები</div>
        </div>
        {tab === 'employees' && (
          <button className="btn btn-primary" onClick={() => setModal({ open: true })}>+ ახალი</button>
        )}
      </div>

      <div className="approval-toolbar">
        <div className="tabs">
          <button className={`tab-btn${tab === 'employees' ? ' tab-btn--active' : ''}`} onClick={() => setTab('employees')}>👥 თანამშრომლები</button>
          <button className={`tab-btn${tab === 'calc' ? ' tab-btn--active' : ''}`} onClick={() => setTab('calc')}>🧮 კალკულატორი</button>
        </div>
        {tab === 'employees' && (
          <select className="input" value={status} onChange={e => setStatus(e.target.value)} style={{ width: 140 }}>
            <option value="active">აქტიური</option>
            <option value="inactive">არააქტიური</option>
            <option value="">ყველა</option>
          </select>
        )}
      </div>

      {tab === 'employees' && (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>სახელი</th><th>პოზიცია</th><th>დეპარტამენტი</th><th>ხელფასი</th><th>სტატუსი</th><th></th></tr></thead>
              <tbody>
                {isLoading ? <tr><td colSpan={6} style={{ textAlign: 'center', padding: 32 }}><span className="spinner" /></td></tr>
                  : employees.length === 0 ? <tr><td colSpan={6}><div className="empty-state"><div className="empty-ic">👥</div><div className="empty-txt">თანამშრომელი არ არის</div></div></td></tr>
                  : employees.map(e => (
                    <tr key={e.id}>
                      <td style={{ fontWeight: 600 }}>{e.name}</td>
                      <td className="text-soft">{e.position || '—'}</td>
                      <td className="text-soft">{e.department || '—'}</td>
                      <td className="num">₾{Number(e.salary).toLocaleString('ka-GE', { maximumFractionDigits: 0 })}</td>
                      <td><span className={`badge ${e.status === 'active' ? 'badge-approved' : 'badge-rejected'}`}>{e.status}</span></td>
                      <td>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button className="btn btn-ghost btn-sm" onClick={() => setModal({ open: true, emp: e })}>✏️</button>
                          <button className="btn btn-danger btn-sm" onClick={() => { if (window.confirm('წაშლა?')) deleteMut.mutate(e.id); }}>🗑</button>
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'calc' && <PayrollCalc />}
    </div>
  );
}
