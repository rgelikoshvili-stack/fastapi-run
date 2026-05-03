import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Approval from './pages/Approval';
import PlaceholderPage from './pages/PlaceholderPage';
import './styles/globals.css';

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30000,
      refetchOnWindowFocus: false,
    },
  },
});

const PAGES = [
  { path: 'documents',    title: 'Documents',          icon: '📄', legacy: '/documents.html' },
  { path: 'journal',      title: 'Journal',             icon: '📒', legacy: '/journal.html' },
  { path: 'coa',          title: 'Chart of Accounts',   icon: '🗂', legacy: '/drafts.html' },
  { path: 'reports',      title: 'Financial Reports',   icon: '📊', legacy: '/financial_reports.html' },
  { path: 'inventory',    title: 'Inventory',           icon: '📦', legacy: '/inventory.html' },
  { path: 'payroll',      title: 'Payroll',             icon: '👥', legacy: '/employees.html' },
  { path: 'assets',       title: 'Fixed Assets',        icon: '🏗', legacy: '/fixed_assets.html' },
  { path: 'budget',       title: 'Budget Planning',     icon: '💰', legacy: '/budget_planning.html' },
  { path: 'vat',          title: 'VAT Declaration',     icon: '📋', legacy: '/vat_declaration.html' },
  { path: 'currency',     title: 'Currency Rates',      icon: '💱', legacy: '/approval.html' },
  { path: 'integrations', title: 'Integrations',        icon: '🔗', legacy: '/integrations.html' },
  { path: 'settings',     title: 'Settings',            icon: '⚙',  legacy: '/settings.html' },
];

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/app/login" element={<Login />} />
            <Route path="/app" element={<Layout />}>
              <Route index element={<Navigate to="/app/dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="approval"  element={<Approval />} />
              {PAGES.map(({ path, title, icon, legacy }) => (
                <Route
                  key={path}
                  path={path}
                  element={<PlaceholderPage title={title} icon={icon} legacyPath={legacy} />}
                />
              ))}
              <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
            </Route>
            <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
