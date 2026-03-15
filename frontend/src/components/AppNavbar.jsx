import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { logout as apiLogout } from '../services/api';
import { LogOut, Zap, Settings } from 'lucide-react';

export default function AppNavbar() {
  const { user, logoutUser } = useAuth();
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
