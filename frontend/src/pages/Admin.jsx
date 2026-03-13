import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import {
  createUser, listUsers, deleteUser,
  uploadHistoricalAds, uploadBrandUSP,
  getAuditLogs, getUsageStats,
  logout as apiLogout,
} from '../services/api';
import toast from 'react-hot-toast';
import { LogOut, Users, Upload, Activity, ArrowLeft, Trash2 } from 'lucide-react';

export default function Admin() {
  const { user, logoutUser } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('users');
  const [users, setUsers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState({});
  const [newUser, setNewUser] = useState({ full_name: '', email: '', password: '', role: 'user' });

  useEffect(() => {
    if (user?.role !== 'admin') {
      navigate('/');
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

  const handleUpload = async (type, file) => {
    try {
      const fn = type === 'historical' ? uploadHistoricalAds : uploadBrandUSP;
      const res = await fn(file);
      toast.success(`${res.data.rows_processed} rows processed. Hotels: ${res.data.hotels_found.join(', ')}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    }
  };

  const handleLogout = async () => {
    try { await apiLogout(); } catch {}
    logoutUser();
    navigate('/login');
  };

  return (
    <div className="dashboard">
      <nav className="topbar">
        <div className="topbar-brand">
          <button className="btn btn-sm btn-outline" onClick={() => navigate('/')}>
            <ArrowLeft size={16} /> Back
          </button>
          <span>Admin Portal</span>
        </div>
        <div className="topbar-user">
          <span>{user?.full_name}</span>
          <button className="btn btn-sm btn-outline" onClick={handleLogout}>
            <LogOut size={16} /> Logout
          </button>
        </div>
      </nav>

      <main className="main-content">
        <div className="admin-tabs">
          <button className={`tab ${tab === 'users' ? 'active' : ''}`} onClick={() => { setTab('users'); loadUsers(); }}>
            <Users size={16} /> Users
          </button>
          <button className={`tab ${tab === 'upload' ? 'active' : ''}`} onClick={() => setTab('upload')}>
            <Upload size={16} /> Data Upload
          </button>
          <button className={`tab ${tab === 'logs' ? 'active' : ''}`} onClick={() => { setTab('logs'); loadLogs(); loadStats(); }}>
            <Activity size={16} /> Audit & Usage
          </button>
        </div>

        {tab === 'users' && (
          <div className="admin-panel">
            <h3>Create User</h3>
            <form onSubmit={handleCreateUser} className="inline-form">
              <input placeholder="Full Name" value={newUser.full_name} onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })} required />
              <input placeholder="Email" type="email" value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} required />
              <input placeholder="Password" type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} required minLength={8} />
              <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
              <button type="submit" className="btn btn-primary">Create</button>
            </form>

            <h3>Users</h3>
            <table className="data-table">
              <thead>
                <tr><th>Name</th><th>Email</th><th>Role</th><th>Created</th><th></th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.uid}>
                    <td>{u.full_name}</td>
                    <td>{u.email}</td>
                    <td><span className={`badge badge-${u.role}`}>{u.role}</span></td>
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

        {tab === 'upload' && (
          <div className="admin-panel">
            <div className="upload-section">
              <h3>Historical Ad Data CSV</h3>
              <p>Upload ad platform export CSVs with headlines, descriptions, CTR, and CVR columns.</p>
              <input type="file" accept=".csv" onChange={(e) => e.target.files[0] && handleUpload('historical', e.target.files[0])} />
            </div>
            <div className="upload-section">
              <h3>Brand & USP CSV</h3>
              <p>Upload CSV with Hotel Name, USPs, Positive Keywords, Negative Keywords, Restricted Keywords.</p>
              <input type="file" accept=".csv" onChange={(e) => e.target.files[0] && handleUpload('brand', e.target.files[0])} />
            </div>
          </div>
        )}

        {tab === 'logs' && (
          <div className="admin-panel">
            <h3>Usage Stats by User</h3>
            <table className="data-table">
              <thead>
                <tr><th>Email</th><th>Logins</th><th>Generations</th><th>Total Tokens</th></tr>
              </thead>
              <tbody>
                {Object.entries(stats).map(([email, s]) => (
                  <tr key={email}>
                    <td>{email}</td>
                    <td>{s.login_count}</td>
                    <td>{s.generations}</td>
                    <td>{s.total_tokens?.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h3>Recent Audit Logs</h3>
            <table className="data-table">
              <thead>
                <tr><th>Time</th><th>User</th><th>Action</th><th>Tokens</th></tr>
              </thead>
              <tbody>
                {logs.map((l) => (
                  <tr key={l.id}>
                    <td>{new Date(l.timestamp).toLocaleString()}</td>
                    <td>{l.user_email}</td>
                    <td><span className={`badge badge-${l.action}`}>{l.action}</span></td>
                    <td>{l.tokens_consumed || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
