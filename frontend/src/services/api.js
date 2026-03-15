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

// Admin - Export
export const exportUsageCSV = () => api.get('/admin/export/usage', { responseType: 'blob' });

// Admin - Settings
export const getAdminSettings = () => api.get('/admin/settings');
export const updateAdminSettings = (data) => api.put('/admin/settings', data);

// Generate
export const generateAds = (data) => api.post('/generate', data);
export const refineAds = (data) => api.post('/generate/refine', data);
export const getUrlSuggestions = (query) => api.get(`/generate/url-suggestions?query=${encodeURIComponent(query)}`);

// Places
export const placesAutocomplete = (query) => api.get(`/places/autocomplete?query=${encodeURIComponent(query)}`);

// Training (Admin)
export const startTraining = (file, csvType, hotelName = '') => {
  const form = new FormData();
  form.append('file', file);
  form.append('csv_type', csvType);
  if (hotelName) form.append('hotel_name', hotelName);
  return api.post('/training/upload', form);
};
export const answerTraining = (data) => api.post('/training/answer', data);
export const getTrainingSessions = () => api.get('/training/sessions');
export const getTrainingDirectives = (hotelName) => api.get(`/training/directives/${encodeURIComponent(hotelName)}`);
export const deleteTrainingDirective = (hotelName, type) => api.delete(`/training/directives/${encodeURIComponent(hotelName)}/${type}`);

// Events
export const searchEvents = (data) => api.post('/events/search', data);

// CRM
export const generateCRM = (data) => api.post('/crm/generate', data);
export const refineCRM = (data) => api.post('/crm/refine', data);
export const exportCRMCalendar = (data) => api.post('/crm/export-calendar', data, { responseType: 'blob' });

export default api;
