export interface ApiResponse<T = unknown> {
  ok: boolean;
  message?: string;
  data?: T;
  error?: string;
}

export interface Draft {
  id: string;
  date: string;
  description: string;
  amount: number;
  status: 'pending_approval' | 'approved' | 'auto_approved' | 'rejected';
  confidence: number;
  account_code?: string;
  debit_account?: string;
  credit_account?: string;
  source_type?: string;
  created_at: string;
  tenant_id?: string;
}

export interface KPI {
  total_drafts: number;
  pending: number;
  approved: number;
  auto_approved: number;
  rejected: number;
  last_24h: number;
  auto_approval_rate: number;
  approval_rate: number;
  avg_confidence: number;
  active_patterns: number;
  total_feedback: number;
}

export interface PnL {
  income: number;
  expenses: number;
  profit: number;
  profit_margin: number;
}

export interface CashflowChart {
  labels: string[];
  inflow: number[];
  outflow: number[];
}

export interface ExchangeRate {
  currency: string;
  rate: number;
  fetched_at?: string;
}

export interface Document {
  id: string;
  file_name: string;
  doc_type: string;
  status: string;
  uploaded_at: string;
  tenant_id?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
  token_type: string;
}

export interface UserInfo {
  email: string;
  role: string;
  tenant_id: string;
}

export interface QueueResponse {
  queue?: Draft[];
  items?: Draft[];
  count?: number;
  total?: number;
}
