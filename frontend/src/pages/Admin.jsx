import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import {
  createUser, listUsers, deleteUser,
  getAuditLogs, getUsageStats,
  getAdminSettings, updateAdminSettings,
  exportUsageCSV,
} from '../services/api';
import toast from 'react-hot-toast';
import TrainingWizard from '../components/TrainingWizard';
import UserForm from '../components/admin/UserForm';
import HotelsIngestion from './admin/HotelsIngestion';
import KnowledgeBase from './admin/KnowledgeBase';
import { Users, Activity, Trash2, Settings, Download, Brain, Building, BookOpen } from 'lucide-react';

export default function Admin() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('users');
  const [users, setUsers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState({});
  const [newUser, setNewUser] = useState({ full_name: '', email: '', password: '', role: 'user' });

  // Settings state
  const [settings, setSettings] = useState({ default_model: 'gemini-2.5-flash' });
  const [availableModels, setAvailableModels] = useState([]);
  const [savingSettings, setSavingSettings] = useState(false);

  useEffect(() => {
    if (user?.role !== 'admin') {
      navigate('/adcopy');
      return;
    }
    loadUsers();
  }, []);

  const loadUsers = async () => {
    try {
      const res = await listUsers();
      setUsers(res.data);
    } catch {}
  };

  const loadLogs = async () => {
    try {
      const res = await getAuditLogs();
      setLogs(res.data);
    } catch {}
  };

  const loadStats = async () => {
    try {
      const res = await getUsageStats();
      setStats(res.data);
    } catch {}
  };

  const loadSettings = async () => {
    try {
      const res = await getAdminSettings();
      setSettings(res.data.settings || { default_model: 'gemini-2.5-flash' });
      setAvailableModels(res.data.available_models || []);
    } catch (err) {
      toast.error('Failed to load settings');
    }
  };

  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      await updateAdminSettings(settings);
      toast.success('Settings saved successfully');
    } catch (err) {
      toast.error('Failed to save settings');
    } finally {
      setSavingSettings(false);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    try {
      await createUser(newUser);
      toast.success('User created');
      setNewUser({ full_name: '', email: '', password: '', role: 'user' });
      loadUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create user');
    }
  };

  const handleDeleteUser = async (id) => {
    if (!window.confirm('Delete this user?')) return;
    try {
      await deleteUser(id);
      toast.success('User deleted');
      loadUsers();
    } catch (err) {
      toast.error('Failed to delete user');
    }
  };

  const handleExport = async () => {
    try {
      const res = await exportUsageCSV();
      const blob = new Blob([res.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `usage_export_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Usage data exported!');
    } catch (err) {
      toast.error('Export failed');
    }
  };

  return (
    <>
      <div className="page-header">
        <h1>Admin Panel</h1>
      </div>

        <div className="admin-tabs">
          <button className={`tab ${tab === 'users' ? 'active' : ''}`} onClick={() => { setTab('users'); loadUsers(); }}>
            <Users size={16} /> <span className="tab-label">Users</span>
          </button>
          <button className={`tab ${tab === 'training' ? 'active' : ''}`} onClick={() => setTab('training')}>
            <Brain size={16} /> <span className="tab-label">Training</span>
          </button>
          <button className={`tab ${tab === 'logs' ? 'active' : ''}`} onClick={() => { setTab('logs'); loadLogs(); loadStats(); }}>
            <Activity size={16} /> <span className="tab-label">Audit & Usage</span>
          </button>
          <button className={`tab ${tab === 'hotels' ? 'active' : ''}`} onClick={() => setTab('hotels')}>
            <Building size={16} /> <span className="tab-label">Hotels Ingestion</span>
          </button>
          <button className={`tab ${tab === 'knowledge' ? 'active' : ''}`} onClick={() => setTab('knowledge')}>
            <BookOpen size={16} /> <span className="tab-label">Knowledge Base</span>
          </button>
          <button className={`tab ${tab === 'settings' ? 'active' : ''}`} onClick={() => { setTab('settings'); loadSettings(); }}>
            <Settings size={16} /> <span className="tab-label">LLM Settings</span>
          </button>
        </div>

        {tab === 'users' && (
          <div className="admin-panel">
            <UserForm onSaved={() => { loadUsers(); }} />

            <h3 style={{ marginTop: 24 }}>Users</h3>
            <table className="data-table">
              <thead>
                <tr><th>Name</th><th>Email</th><th>Role</th><th>Scope</th><th>Visibility</th><th>Created</th><th></th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.uid}>
                    <td>{u.full_name}</td>
                    <td>{u.email}</td>
                    <td><span className={`badge badge-${u.role}`}>{(u.role || '').replace('_', ' ')}</span></td>
                    <td style={{ fontSize: 12, color: 'var(--em-ink-soft, #595650)' }}>
                      {u.scope_summary
                        ? `${u.scope_summary.brand_count || 0}b · ${u.scope_summary.hotel_count || 0}h`
                        : (u.role === 'admin' ? 'all' : '—')}
                    </td>
                    <td style={{ fontSize: 11 }}>
                      {u.show_token_count ? '#' : '—'}{' '}
                      {u.show_token_amount ? '₹' : '—'}
                    </td>
                    <td>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '-'}</td>
                    <td>
                      <button className="btn-icon danger" onClick={() => handleDeleteUser(u.uid)}>
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === 'training' && (
          <TrainingWizard />
        )}

        {tab === 'hotels' && (
          <div className="admin-panel">
            <HotelsIngestion />
          </div>
        )}

        {tab === 'knowledge' && (
          <div className="admin-panel">
            <KnowledgeBase />
          </div>
        )}

        {tab === 'logs' && (
          <div className="admin-panel">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ marginBottom: 0 }}>Usage Stats by User</h3>
              <button className="btn btn-sm btn-outline" onClick={handleExport}>
                <Download size={14} /> Export All Usage (CSV)
              </button>
            </div>
            <table className="data-table">
              <thead>
                <tr><th>Email</th><th>Logins</th><th>Generations</th><th>Total Tokens</th><th>Total Cost (INR)</th></tr>
              </thead>
              <tbody>
                {Object.entries(stats).map(([email, s]) => (
                  <tr key={email}>
                    <td>{email}</td>
                    <td>{s.login_count}</td>
                    <td>{s.generations}</td>
                    <td>{s.total_tokens?.toLocaleString()}</td>
                    <td style={{ color: 'var(--gold)' }}>{s.total_cost_inr != null ? `₹${s.total_cost_inr.toFixed(4)}` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h3>Recent Audit Logs</h3>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr><th>Time</th><th>User</th><th>Action</th><th>Hotel</th><th>Tokens</th><th>Cost (INR)</th></tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id}>
                      <td style={{ whiteSpace: 'nowrap' }}>{new Date(l.timestamp).toLocaleString()}</td>
                      <td>{l.user_email}</td>
                      <td><span className={`badge badge-${l.action}`}>{l.action}</span></td>
                      <td>{l.hotel_name || '-'}</td>
                      <td>{l.tokens_consumed || '-'}</td>
                      <td style={{ color: 'var(--gold)' }}>{l.action === 'generate' && l.cost_inr != null ? `₹${l.cost_inr.toFixed(4)}` : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'settings' && (
          <div className="admin-panel">
            <h3>LLM Model Configuration</h3>
            <p style={{ marginBottom: '1.25rem', fontSize: '0.85rem' }}>
              Select the default AI model used for all ad copy generation. This setting applies globally to all users.
            </p>
            <div className="settings-group">
              <div className="settings-row">
                <label>Default LLM Model</label>
                <select
                  value={settings.default_model}
                  onChange={(e) => setSettings({ ...settings, default_model: e.target.value })}
                >
                  {availableModels.map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
              </div>
              <button
                className="btn btn-primary"
                onClick={handleSaveSettings}
                disabled={savingSettings}
                style={{ alignSelf: 'flex-start' }}
              >
                {savingSettings ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>
        )}
    </>
  );
}
