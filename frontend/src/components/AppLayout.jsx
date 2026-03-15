import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../contexts/ThemeContext';
import { logout as apiLogout } from '../services/api';
import { Zap, Megaphone, Mail, Settings, LogOut, Sun, Moon } from 'lucide-react';

export default function AppLayout() {
  const { user, logoutUser } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try { await apiLogout(); } catch {}
    logoutUser();
    navigate('/login');
  };

  const initials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : '?';

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Zap size={20} className="sidebar-brand-icon" />
          <span className="sidebar-brand-name">Vantage GenAI</span>
        </div>

        <nav className="sidebar-nav">
          <NavLink
            to="/adcopy"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <Megaphone size={18} />
            <span>Ad Copy</span>
          </NavLink>
          <NavLink
            to="/crm"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <Mail size={18} />
            <span>CRM</span>
          </NavLink>
          {user?.role === 'admin' && (
            <NavLink
              to="/admin"
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <Settings size={18} />
              <span>Admin</span>
            </NavLink>
          )}
        </nav>

        <div className="sidebar-footer">
          <button
            className="sidebar-link"
            onClick={toggleTheme}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
          </button>

          <div className="sidebar-user">
            <div className="sidebar-user-avatar">{initials}</div>
            <span className="sidebar-user-name">{user?.full_name}</span>
          </div>

          <button className="sidebar-link sidebar-logout" onClick={handleLogout}>
            <LogOut size={18} />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
