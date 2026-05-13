import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── 401 handler ────────────────────────────────────────
// Uses soft SPA navigation instead of window.location.href which
// would cause a full page reload, destroying all React state and cache.
let _navigate = null;

/**
 * Register the React Router navigate function for SPA-safe 401 redirects.
 * Called once from AuthContext on mount.
 */
export function registerNavigate(navigateFn) {
  _navigate = navigateFn;
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    // Handle both 401 (expired/invalid token) and 403 (no matching employee)
    if (status === 401 || status === 403) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      // SPA-safe redirect — no full page reload
      if (_navigate) {
        _navigate('/login', { replace: true });
      } else {
        // Fallback only if navigate hasn't been registered yet
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;
