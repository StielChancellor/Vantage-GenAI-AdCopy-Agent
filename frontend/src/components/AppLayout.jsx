import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../contexts/ThemeContext';
import { logout as apiLogout } from '../services/api';
import { Zap, Megaphone, Mail, Settings, LogOut, Sun, Moon, User, Building, BookOpen } from 'lucide-react';
import { APP_VERSION, APP_VERSION_DATE } from '../version';

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

  const isAdmin = user?.role === 'admin';
  const niceRole = (user?.role || '').replace(/_/g, ' ');

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Zap size={20} className="sidebar-brand-icon" />
          <span className="sidebar-brand-name">Vantage GenAI</span>
        </div>

        <nav className="sidebar-nav">
          <NavLink to="/adcopy" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <Megaphone size={18} />
            <span>Ad Copy</span>
          </NavLink>
          <NavLink to="/crm" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <Mail size={18} />
            <span>CRM</span>
          </NavLink>
          <NavLink to="/account" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <User size={18} />
            <span>My Account</span>
          </NavLink>

          {isAdmin && (
            <>
              <div className="em-mono-label" style={{ marginTop: 14, padding: '4px 12px' }}>Admin</div>
              <NavLink to="/admin" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`} end>
                <Settings size={18} />
                <span>Users & Settings</span>
              </NavLink>
              <NavLink to="/admin/hotels" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
                <Building size={18} />
                <span>Hotels Ingestion</span>
              </NavLink>
              <NavLink to="/admin/knowledge" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
                <BookOpen size={18} />
                <span>Knowledge Base</span>
              </NavLink>
            </>
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
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <span className="sidebar-user-name">{user?.full_name}</span>
              <span style={{ fontSize: 10.5, color: 'var(--em-ink-faint, #908c84)', textTransform: 'capitalize', letterSpacing: '0.04em' }}>
                {niceRole}
              </span>
            </div>
          </div>

          <button className="sidebar-link sidebar-logout" onClick={handleLogout}>
            <LogOut size={18} />
            <span>Logout</span>
          </button>

          <div className="em-version-footer">
            App v{APP_VERSION} · {APP_VERSION_DATE}
          </div>
        </div>
      </aside>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
