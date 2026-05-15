import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../contexts/ThemeContext';
import { logout as apiLogout } from '../services/api';
import { Zap, Megaphone, Mail, Settings, LogOut, Sun, Moon, User, Building, BookOpen, Home, Calendar, Sparkles } from 'lucide-react';
import { APP_VERSION, APP_VERSION_DATE } from '../version';
import TweaksPanel from './TweaksPanel';

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
          <NavLink to="/hub" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <Home size={18} />
            <span>Home</span>
          </NavLink>
          <NavLink to="/ideation" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <Sparkles size={18} />
            <span>Campaign Ideation</span>
          </NavLink>
          <NavLink to="/unified" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <Zap size={18} />
            <span>Unified Campaign</span>
          </NavLink>
          <NavLink to="/adcopy" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <Megaphone size={18} />
            <span>Ad Copy</span>
          </NavLink>
          <NavLink to="/crm" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <Mail size={18} />
            <span>CRM</span>
          </NavLink>
          <NavLink to="/calendar" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <Calendar size={18} />
            <span>Marketing Calendar</span>
          </NavLink>
          <NavLink to="/account" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <User size={18} />
            <span>My Account</span>
          </NavLink>

          {isAdmin && (
            <>
              <div className="em-mono-label" style={{ marginTop: 14, padding: '4px 12px' }}>Admin</div>
              <NavLink to="/admin" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
                <Settings size={18} />
                <span>Users & Settings</span>
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
        <TweaksPanel />
      </main>
    </div>
  );
}
