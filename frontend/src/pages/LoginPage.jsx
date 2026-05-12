import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useTheme } from '../lib/ThemeProvider';
import { Sun, Moon, Eye, EyeOff, Shield, User, Lock, AlertCircle, Loader2 } from 'lucide-react';

export default function LoginPage() {
  const { login, loading } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();

  const [employeeCode, setEmployeeCode] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [shake, setShake] = useState(false);

  const codeInputRef = useRef(null);

  // Auto-focus employee code on mount
  useEffect(() => {
    codeInputRef.current?.focus();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setShake(false);

    // Client-side validation
    if (!employeeCode.trim()) {
      setError('Employee code is required.');
      triggerShake();
      return;
    }
    if (!password) {
      setError('Password is required.');
      triggerShake();
      return;
    }

    const result = await login(employeeCode, password);

    if (result.success) {
      navigate('/', { replace: true });
    } else {
      setError(result.error);
      triggerShake();
    }
  };

  const triggerShake = () => {
    setShake(true);
    setTimeout(() => setShake(false), 600);
  };

  return (
    <div className="login-page">
      {/* Theme toggle */}
      <button
        type="button"
        onClick={toggle}
        className="login-theme-toggle"
        aria-label="Toggle theme"
      >
        {theme === 'dark' ? (
          <Sun className="h-4 w-4 text-amber-400" style={{ color: '#fbbf24' }} />
        ) : (
          <Moon className="h-4 w-4 text-muted" style={{ color: 'var(--color-text-muted)' }} />
        )}
      </button>

      <div className="login-container animate-in">
        {/* Logo / Branding */}
        <div className="login-logo">
          <Shield size={32} strokeWidth={2.5} />
        </div>

        <h1 className="login-title">
          <span className="login-title-accent">A</span>TRACK
        </h1>
        <p className="login-subtitle">
          Employee Attendance Intelligence
        </p>

        {/* Login Form */}
        <form onSubmit={handleSubmit} className={`login-form ${shake ? 'shake' : ''}`}>
          {/* Error Alert */}
          {error && (
            <div className="login-error" role="alert">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Employee Code */}
          <div className="form-group">
            <label htmlFor="employee-code" className="form-label">
              Employee Code
            </label>
            <div className="input-wrapper">
              <User size={18} className="input-icon" />
              <input
                ref={codeInputRef}
                id="employee-code"
                type="text"
                className="form-input"
                placeholder="e.g. EMP001"
                value={employeeCode}
                onChange={(e) => setEmployeeCode(e.target.value.toUpperCase())}
                autoComplete="username"
                disabled={loading}
              />
            </div>
          </div>

          {/* Password */}
          <div className="form-group">
            <label htmlFor="login-password" className="form-label">
              Password
            </label>
            <div className="input-wrapper">
              <Lock size={18} className="input-icon" />
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                className="form-input has-toggle"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                disabled={loading}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            className="login-submit"
            disabled={loading}
            id="btn-enterprise-login"
          >
            {loading ? (
              <>
                <Loader2 size={18} className="spinner" />
                Signing in…
              </>
            ) : (
              'Sign In'
            )}
          </button>
        </form>

        <p className="login-footer-text">
          Secure enterprise authentication
        </p>
      </div>
    </div>
  );
}
