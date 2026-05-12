import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';

/**
 * RoleGuard Component for strict Role-Based Access Control.
 * @param {Array<string>} allowedRoles - Array of roles allowed to view the children.
 */
export default function RoleGuard({ allowedRoles, children }) {
  const { user, loading } = useAuth();

  if (loading) return null;

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!allowedRoles.includes(user.role)) {
    // If user tries to access a protected route without permissions,
    // redirect them to their main dashboard.
    return <Navigate to="/" replace />;
  }

  return children;
}
