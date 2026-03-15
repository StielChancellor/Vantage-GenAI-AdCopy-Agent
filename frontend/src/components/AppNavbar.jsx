import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../contexts/ThemeContext';
import { logout as apiLogout } from '../services/api';
import { LogOut, Zap, Settings, Sun, Moon } from 'lucide-react';

export default function AppNavbar() {
  const { user, logoutUser } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    try {
      await apiLogout();
    } catch {}
    logoutUser();
    navigate('/login');
  };

  const isActive = (path) => location.pathname === path;

  return (
    <nav className="topbar">
      <div className="topbar-brand">
        <Zap size={20} />
        <span>Vantage GenAI</span>
      </div>

      <div className="topbar-tabs">
        <button
          className={`topbar-tab ${isActive('/adcopy') ? 'active' : ''}`}
          onClick={() => navigate('/adcopy')}
        >
          Ad Copy
        </button>
        <button
          className={`topbar-tab ${isActive('/crm') ? 'active' : ''}`}
          onClick={() => navigate('/crm')}
        >
          CRM
        </button>
      </div>

      <button className="btn-icon theme-toggle" onClick={toggleTheme}
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
        {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      <div className="topbar-user">
        <span>{user?.full_name}</span>
        {user?.role === 'admin' && (
          <button className="btn btn-sm" onClick={() => navigate('/admin')}>
            <Settings size={14} /> Admin
          </button>
        )}
        <button className="btn btn-sm btn-outline" onClick={handleLogout}>
          <LogOut size={16} /> Logout
        </button>
      </div>
    </nav>
  );
}
