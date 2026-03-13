import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { generateAds } from '../services/api';
import toast from 'react-hot-toast';
import AdResults from '../components/AdResults';
import { LogOut, Zap } from 'lucide-react';
import { logout as apiLogout } from '../services/api';
import { useNavigate } from 'react-router-dom';

const PLATFORMS = [
  { id: 'google_search', label: 'Google Search' },
  { id: 'meta_carousel', label: 'Meta Carousel' },
  { id: 'pmax', label: 'Performance Max' },
  { id: 'youtube', label: 'YouTube' },
];

const MODELS = [
  { id: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
  { id: 'gemini-2.0-flash-lite', label: 'Gemini 2.0 Flash Lite' },
  { id: 'gemini-2.5-flash-preview-05-20', label: 'Gemini 2.5 Flash' },
  { id: 'gemini-2.5-pro-preview-05-06', label: 'Gemini 2.5 Pro' },
];

const OBJECTIVES = ['', 'Awareness', 'Consideration', 'Conversion'];

export default function Dashboard() {
  const { user, logoutUser } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    hotel_name: '',
    offer_name: '',
    inclusions: '',
    reference_url: '',
    google_listing_url: '',
    other_info: '',
    campaign_objective: '',
    model_name: 'gemini-2.0-flash',
    platforms: ['google_search'],
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const togglePlatform = (pid) => {
    setForm((prev) => ({
      ...prev,
      platforms: prev.platforms.includes(pid)
        ? prev.platforms.filter((p) => p !== pid)
        : [...prev.platforms, pid],
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.platforms.length === 0) {
      toast.error('Select at least one platform');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const res = await generateAds(form);
      setResult(res.data);
      toast.success(`Generated! ${res.data.tokens_used} tokens used.`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Generation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await apiLogout();
    } catch {}
    logoutUser();
    navigate('/login');
  };

  return (
    <div className="dashboard">
      <nav className="topbar">
        <div className="topbar-brand">
          <Zap size={20} />
          <span>Vantage AdCopy</span>
        </div>
        <div className="topbar-user">
          <span>{user?.full_name}</span>
          {user?.role === 'admin' && (
            <button className="btn btn-sm" onClick={() => navigate('/admin')}>
              Admin
            </button>
          )}
          <button className="btn btn-sm btn-outline" onClick={handleLogout}>
            <LogOut size={16} /> Logout
          </button>
        </div>
      </nav>

      <main className="main-content">
        <div className="content-grid">
          <section className="form-panel">
            <h2>Generate Ad Copy</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Hotel Name *</label>
                <input name="hotel_name" value={form.hotel_name} onChange={handleChange} required placeholder="e.g., The Grand Hyatt" />
              </div>
              <div className="form-group">
                <label>Offer Name *</label>
                <input name="offer_name" value={form.offer_name} onChange={handleChange} required placeholder="e.g., Summer Escape Package" />
              </div>
              <div className="form-group">
                <label>Inclusions *</label>
                <input name="inclusions" value={form.inclusions} onChange={handleChange} required placeholder="e.g., 20% off + breakfast + spa access" />
              </div>
              <div className="form-group">
                <label>Reference URL *</label>
                <input name="reference_url" type="url" value={form.reference_url} onChange={handleChange} required placeholder="https://hotel-website.com" />
              </div>
              <div className="form-group">
                <label>Google Listing URL *</label>
                <input name="google_listing_url" value={form.google_listing_url} onChange={handleChange} required placeholder="https://maps.google.com/..." />
              </div>
              <div className="form-group">
                <label>Other Information</label>
                <textarea name="other_info" value={form.other_info} onChange={handleChange} rows={2} placeholder="Any additional context..." />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Campaign Objective</label>
                  <select name="campaign_objective" value={form.campaign_objective} onChange={handleChange}>
                    {OBJECTIVES.map((o) => (
                      <option key={o} value={o}>{o || 'Auto-detect'}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>LLM Model</label>
                  <select name="model_name" value={form.model_name} onChange={handleChange}>
                    {MODELS.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label>Platforms</label>
                <div className="checkbox-grid">
                  {PLATFORMS.map((p) => (
                    <label key={p.id} className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={form.platforms.includes(p.id)}
                        onChange={() => togglePlatform(p.id)}
                      />
                      {p.label}
                    </label>
                  ))}
                </div>
              </div>
              <button type="submit" className="btn btn-primary btn-full" disabled={loading}>
                {loading ? 'Generating...' : 'Generate Ad Copy'}
              </button>
            </form>
          </section>

          <section className="results-panel">
            {result ? (
              <AdResults data={result} />
            ) : (
              <div className="empty-state">
                <Zap size={48} />
                <h3>Ready to Generate</h3>
                <p>Fill in hotel details and click Generate to create optimized ad copy.</p>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
