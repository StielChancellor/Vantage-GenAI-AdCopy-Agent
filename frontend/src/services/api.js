import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || (
  window.location.hostname === 'localhost' ? 'http://localhost:8000/api/v1' : '/api/v1'
);

const api = axios.create({
  baseURL: API_BASE,
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// Auth
export const login = (email, password) => api.post('/auth/login', { email, password });
export const logout = () => api.post('/auth/logout');
export const getMe = () => api.get('/auth/me');

// Admin - Users
export const createUser = (data) => api.post('/admin/users', data);
export const listUsers = () => api.get('/admin/users');
export const deleteUser = (id) => api.delete(`/admin/users/${id}`);
export const updateUser = (id, data) => api.put(`/admin/users/${id}`, data);

// Admin - CSV Upload
export const uploadHistoricalAds = (file) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/admin/upload/historical-ads', form);
};
export const uploadBrandUSP = (file) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/admin/upload/brand-usp', form);
};

// Admin - Audit
export const getAuditLogs = (limit = 100) => api.get(`/admin/audit-logs?limit=${limit}`);
export const getUsageStats = () => api.get('/admin/usage-stats');

// Generate
export const generateAds = (data) => api.post('/generate', data);

export default api;
