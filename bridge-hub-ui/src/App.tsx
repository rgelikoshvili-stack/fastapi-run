import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Approval from './pages/Approval';
import Journal from './pages/Journal';
import Documents from './pages/Documents';
import Reports from './pages/Reports';
import Inventory from './pages/Inventory';
import Payroll from './pages/Payroll';
import FixedAssets from './pages/FixedAssets';
import Budget from './pages/Budget';
import VAT from './pages/VAT';
import COA from './pages/COA';
import Currency from './pages/Currency';
import Settings from './pages/Settings';
import Integrations from './pages/Integrations';
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

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/app/login" element={<Login />} />
            <Route path="/app" element={<Layout />}>
              <Route index element={<Navigate to="/app/dashboard" replace />} />
              <Route path="dashboard"    element={<Dashboard />} />
              <Route path="approval"     element={<Approval />} />
              <Route path="journal"      element={<Journal />} />
              <Route path="documents"    element={<Documents />} />
              <Route path="reports"      element={<Reports />} />
              <Route path="inventory"    element={<Inventory />} />
              <Route path="payroll"      element={<Payroll />} />
              <Route path="assets"       element={<FixedAssets />} />
              <Route path="budget"       element={<Budget />} />
              <Route path="vat"          element={<VAT />} />
              <Route path="coa"          element={<COA />} />
              <Route path="currency"     element={<Currency />} />
              <Route path="settings"     element={<Settings />} />
              <Route path="integrations" element={<Integrations />} />
              <Route path="*"            element={<Navigate to="/app/dashboard" replace />} />
            </Route>
            <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
