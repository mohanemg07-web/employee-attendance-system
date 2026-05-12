import { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api, { registerNavigate } from '../api/client';
import { prefetchCache } from '../lib/cache';

const AuthContext = createContext(null);

/** Fire-and-forget parallel prefetch of all dashboard APIs after login. */
function prefetchDashboards() {
  Promise.allSettled([
    prefetchCache('employee-dashboard-v4', async () => {
      const res = await api.get('/attendance/me/dashboard');
      return res?.data ?? null;
    }),
    prefetchCache('team-dashboard-v2', async () => {
      const now = new Date();
      const res = await api.get('/attendance/team/dashboard', {
        params: {
          target_date: now.toISOString().slice(0, 10),
          month: now.getMonth() + 1,
          year: now.getFullYear(),
        },
      });
      const d = res?.data ?? {};
      return { dashboard: d, monthly: { records: d.members ?? [] } };
    }),
  ]).catch(() => {});
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('user');
    return saved ? JSON.parse(saved) : null;
  });
  const [token, setToken] = useState(() => localStorage.getItem('access_token'));
  const [loading, setLoading] = useState(false);
  const [passwordResetRequired, setPasswordResetRequired] = useState(false);

  // Register React Router navigate for SPA-safe 401 redirects
  const nav = useNavigate();
  useEffect(() => { registerNavigate(nav); }, [nav]);

  // ── Prefetch on existing session (page refresh) ───
  useEffect(() => {
    if (user && token) {
      // User already logged in — prefetch dashboards in background
      prefetchDashboards();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Enterprise login ─────────────────────────────────
  const login = async (employeeCode, password) => {
    setLoading(true);
    try {
      const res = await api.post('/auth/login', {
        employee_code: employeeCode,
        password: password,
      });

      const data = res.data;
      const accessToken = data.access_token;
      const userProfile = data.user;

      // Store auth state
      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('user', JSON.stringify(userProfile));
      setToken(accessToken);
      setUser(userProfile);

      // Check if password reset is required
      if (data.password_reset_required) {
        setPasswordResetRequired(true);
      } else {
        setPasswordResetRequired(false);
        // Start prefetching dashboards
        prefetchDashboards();
      }

      return { success: true, passwordResetRequired: data.password_reset_required };
    } catch (err) {
      const detail = err.response?.data?.detail || 'Login failed. Please try again.';
      const status = err.response?.status;
      return { success: false, error: detail, status };
    } finally {
      setLoading(false);
    }
  };

  // ── Change password ──────────────────────────────────
  const changePassword = async (currentPassword, newPassword) => {
    try {
      await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordResetRequired(false);
      // Now prefetch dashboards
      prefetchDashboards();
      return { success: true };
    } catch (err) {
      const detail = err.response?.data?.detail || 'Password change failed.';
      return { success: false, error: detail };
    }
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    setToken(null);
    setUser(null);
    setPasswordResetRequired(false);
  };

  const isManager = user?.role === 'MANAGER' || user?.role === 'ADMIN';
  const isAdmin = user?.role === 'ADMIN';

  return (
    <AuthContext.Provider value={{
      user, token, loading,
      login, logout, changePassword,
      isManager, isAdmin,
      passwordResetRequired,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
