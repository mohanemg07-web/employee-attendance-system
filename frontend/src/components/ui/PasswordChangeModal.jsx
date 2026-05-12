import { useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { Lock, Eye, EyeOff, AlertCircle, Check, Loader2 } from 'lucide-react';

/**
 * Modal component for mandatory password change (first login).
 * Renders as a full-screen overlay when password_reset_required is true.
 */
export default function PasswordChangeModal() {
  const { changePassword, logout } = useAuth();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Password strength
  const getStrength = (pw) => {
    if (!pw) return { level: 0, label: '', color: '' };
    let score = 0;
    if (pw.length >= 8) score++;
    if (pw.length >= 12) score++;
    if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
    if (/\d/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;

    if (score <= 1) return { level: 1, label: 'Weak', color: 'var(--color-rose)' };
    if (score <= 2) return { level: 2, label: 'Fair', color: 'var(--color-amber)' };
    if (score <= 3) return { level: 3, label: 'Good', color: 'var(--color-accent)' };
    return { level: 4, label: 'Strong', color: 'var(--color-emerald)' };
  };

  const strength = getStrength(newPassword);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!currentPassword) {
      setError('Current password is required.');
      return;
    }
    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    const result = await changePassword(currentPassword, newPassword);
    setLoading(false);

    if (!result.success) {
      setError(result.error);
    }
    // On success, AuthContext will set passwordResetRequired=false,
    // which unmounts this modal automatically.
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content animate-in">
        <div className="modal-icon">
          <Lock size={28} strokeWidth={2} />
        </div>

        <h2 className="modal-title">Change Your Password</h2>
        <p className="modal-subtitle">
          You must set a new password before continuing.
        </p>

        <form onSubmit={handleSubmit} className="login-form">
          {error && (
            <div className="login-error" role="alert">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Current Password */}
          <div className="form-group">
            <label htmlFor="current-pw" className="form-label">Current Password</label>
            <div className="input-wrapper">
              <Lock size={18} className="input-icon" />
              <input
                id="current-pw"
                type={showCurrent ? 'text' : 'password'}
                className="form-input has-toggle"
                placeholder="Enter current password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                disabled={loading}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowCurrent(!showCurrent)}
                tabIndex={-1}
              >
                {showCurrent ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* New Password */}
          <div className="form-group">
            <label htmlFor="new-pw" className="form-label">New Password</label>
            <div className="input-wrapper">
              <Lock size={18} className="input-icon" />
              <input
                id="new-pw"
                type={showNew ? 'text' : 'password'}
                className="form-input has-toggle"
                placeholder="Enter new password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                disabled={loading}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowNew(!showNew)}
                tabIndex={-1}
              >
                {showNew ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {/* Strength indicator */}
            {newPassword && (
              <div className="password-strength">
                <div className="strength-bars">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className="strength-bar"
                      style={{
                        background: i <= strength.level ? strength.color : 'var(--color-border)',
                      }}
                    />
                  ))}
                </div>
                <span className="strength-label" style={{ color: strength.color }}>
                  {strength.label}
                </span>
              </div>
            )}
          </div>

          {/* Confirm Password */}
          <div className="form-group">
            <label htmlFor="confirm-pw" className="form-label">Confirm New Password</label>
            <div className="input-wrapper">
              <Lock size={18} className="input-icon" />
              <input
                id="confirm-pw"
                type="password"
                className="form-input"
                placeholder="Confirm new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                disabled={loading}
              />
              {confirmPassword && confirmPassword === newPassword && (
                <div className="input-check">
                  <Check size={18} style={{ color: 'var(--color-emerald)' }} />
                </div>
              )}
            </div>
          </div>

          <button
            type="submit"
            className="login-submit"
            disabled={loading}
          >
            {loading ? (
              <>
                <Loader2 size={18} className="spinner" />
                Updating…
              </>
            ) : (
              'Update Password'
            )}
          </button>

          <button
            type="button"
            className="modal-logout-btn"
            onClick={logout}
            disabled={loading}
          >
            Sign out instead
          </button>
        </form>
      </div>
    </div>
  );
}
