import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import api from '../api/client';
import type { UserInfo } from '../api/types';

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string, tenantId?: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: localStorage.getItem('bh_token'),
    user: null,
    isLoading: true,
  });

  // On mount, verify token is still valid by fetching user info
  useEffect(() => {
    const token = localStorage.getItem('bh_token');
    if (!token) {
      setState(s => ({ ...s, isLoading: false }));
      return;
    }
    api.get('/auth/me')
      .then(res => {
        setState({ token, user: res.data?.data || res.data, isLoading: false });
      })
      .catch(() => {
        localStorage.removeItem('bh_token');
        localStorage.removeItem('bh_refresh');
        setState({ token: null, user: null, isLoading: false });
      });
  }, []);

  const login = useCallback(async (email: string, password: string, tenantId?: string) => {
    const body: Record<string, string> = { email, password };
    if (tenantId) body.tenant_id = tenantId;
    const res = await api.post('/auth/login', body);
    const { access_token, refresh_token } = res.data?.data || res.data;
    localStorage.setItem('bh_token', access_token);
    if (refresh_token) localStorage.setItem('bh_refresh', refresh_token);
    if (tenantId) localStorage.setItem('bh_tenant', tenantId);
    // Fetch user info after login
    const me = await api.get('/auth/me');
    setState({ token: access_token, user: me.data?.data || me.data, isLoading: false });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('bh_token');
    localStorage.removeItem('bh_refresh');
    setState({ token: null, user: null, isLoading: false });
    window.location.href = '/app/login';
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout, isAuthenticated: !!state.token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
