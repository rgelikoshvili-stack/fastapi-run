import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import './Sidebar.css';

const NAV = [
  { label: 'Dashboard',        path: '/app/dashboard',  icon: '⊞' },
  { label: 'Approval Queue',   path: '/app/approval',   icon: '✓' },
  { label: 'Documents',        path: '/app/documents',  icon: '📄' },
  { label: 'Journal',          path: '/app/journal',    icon: '📒' },
  { label: 'Chart of Accounts',path: '/app/coa',        icon: '🗂' },
  { label: 'Reports',          path: '/app/reports',    icon: '📊' },
  { label: 'Inventory',        path: '/app/inventory',  icon: '📦' },
  { label: 'Payroll',          path: '/app/payroll',    icon: '👥' },
  { label: 'Fixed Assets',     path: '/app/assets',     icon: '🏗' },
  { label: 'Budget',           path: '/app/budget',     icon: '💰' },
  { label: 'VAT Declaration',  path: '/app/vat',        icon: '📋' },
  { label: 'Currency',         path: '/app/currency',   icon: '💱' },
  { label: 'Integrations',     path: '/app/integrations',icon: '🔗' },
  { label: 'Settings',         path: '/app/settings',   icon: '⚙' },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside className={`sidebar${collapsed ? ' sidebar--collapsed' : ''}`}>
      <div className="sidebar__logo">
        <svg viewBox="0 0 40 40" fill="none" width="28" height="28">
          <rect width="40" height="40" rx="8" fill="#8c3c2d"/>
          <path d="M8 28 L20 12 L32 28" stroke="#f3ecdc" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
          <path d="M14 22 L26 22" stroke="#f3ecdc" strokeWidth="2.5" strokeLinecap="round"/>
        </svg>
        {!collapsed && <span className="sidebar__logo-text">Bridge <em>Hub</em></span>}
        <button className="sidebar__collapse-btn" onClick={() => setCollapsed(c => !c)}>
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      <nav className="sidebar__nav">
        {NAV.map(({ label, path, icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) => `sidebar__link${isActive ? ' sidebar__link--active' : ''}`}
            title={collapsed ? label : undefined}
          >
            <span className="sidebar__icon">{icon}</span>
            {!collapsed && <span className="sidebar__label">{label}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar__footer">
        {!collapsed && user && (
          <div className="sidebar__user">
            <div className="sidebar__user-email">{user.email}</div>
            <div className="sidebar__user-role">{user.role}</div>
          </div>
        )}
        <button className="sidebar__logout btn btn-ghost btn-sm" onClick={logout} title="Logout">
          {collapsed ? '⏻' : '⏻ Logout'}
        </button>
      </div>
    </aside>
  );
}
