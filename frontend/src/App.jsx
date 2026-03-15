import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './contexts/ThemeContext';
import { AuthProvider, useAuth } from './hooks/useAuth';
import LandingPage from './pages/LandingPage';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import CRMWizard from './pages/CRMWizard';
import Admin from './pages/Admin';

function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Loading...</div>;
  if (!user) return <Navigate to="/" />;
  if (adminOnly && user.role !== 'admin') return <Navigate to="/adcopy" />;
  return children;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Loading...</div>;

  return (
    <Routes>
      <Route path="/" element={user ? <Navigate to="/adcopy" /> : <LandingPage />} />
      <Route path="/login" element={user ? <Navigate to="/adcopy" /> : <Login />} />
      <Route path="/adcopy" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/crm" element={<ProtectedRoute><CRMWizard /></ProtectedRoute>} />
      <Route path="/admin" element={<ProtectedRoute adminOnly><Admin /></ProtectedRoute>} />
      {/* Backward compatibility redirect */}
      <Route path="/dashboard" element={<Navigate to="/adcopy" replace />} />
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <Toaster position="top-right" />
          <AppRoutes />
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
