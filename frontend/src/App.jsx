import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './contexts/ThemeContext';
import { SelectionProvider } from './contexts/SelectionContext';
import { AuthProvider, useAuth } from './hooks/useAuth';
import LandingPage from './pages/LandingPage';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import CRMWizard from './pages/CRMWizard';
import Admin from './pages/Admin';
import AppLayout from './components/AppLayout';
import MyAccount from './pages/MyAccount';
import HotelsIngestion from './pages/admin/HotelsIngestion';
import KnowledgeBase from './pages/admin/KnowledgeBase';
import Hub from './pages/Hub';
import MarketingCalendar from './pages/MarketingCalendar';
import UnifiedCampaign from './pages/UnifiedCampaign';
import CampaignIdeation from './pages/CampaignIdeation';
import './styles/editorial-mono.css';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Loading...</div>;
  if (!user) return <Navigate to="/" />;
  return children;
}

function RequireAdmin({ children }) {
  const { user } = useAuth();
  if (user?.role !== 'admin') return <Navigate to="/adcopy" />;
  return children;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Loading...</div>;

  return (
    <Routes>
      <Route path="/" element={user ? <Navigate to="/hub" /> : <LandingPage />} />
      <Route path="/login" element={user ? <Navigate to="/hub" /> : <Login />} />

      {/* Authenticated routes with sidebar layout */}
      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/hub" element={<Hub />} />
        <Route path="/adcopy" element={<Dashboard />} />
        <Route path="/crm" element={<CRMWizard />} />
        <Route path="/calendar" element={<MarketingCalendar />} />
        <Route path="/unified" element={<UnifiedCampaign />} />
        <Route path="/ideation" element={<CampaignIdeation />} />
        <Route path="/account" element={<MyAccount />} />
        <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
        <Route path="/admin/hotels" element={<RequireAdmin><HotelsIngestion /></RequireAdmin>} />
        <Route path="/admin/knowledge" element={<RequireAdmin><KnowledgeBase /></RequireAdmin>} />
        {/* Legacy redirect — Creative Assets now lives under Admin → Training */}
        <Route path="/admin/creative-assets" element={<Navigate to="/admin" replace />} />
      </Route>

      {/* Backward compatibility redirect */}
      <Route path="/dashboard" element={<Navigate to="/hub" replace />} />
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <SelectionProvider>
            <Toaster position="top-right" />
            <AppRoutes />
          </SelectionProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
