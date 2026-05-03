import React from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import { useAuth } from '../contexts/AuthContext';
import './Layout.css';

export default function Layout() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="layout-loading">
        <span className="spinner" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/app/login" replace />;
  }

  return (
    <div className="layout">
      <Sidebar />
      <div className="layout__main">
        <Outlet />
      </div>
    </div>
  );
}
