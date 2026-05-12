import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import Layout from './components/Layout/Layout';
import LoginPage from './pages/LoginPage';
import EmployeeDashboard from './pages/EmployeeDashboard';
import ManagerDashboard from './pages/ManagerDashboard';
import AdminPanel from './pages/AdminPanel';
import PasswordChangeModal from './components/ui/PasswordChangeModal';

import RoleGuard from './auth/RoleGuard';

function AppRoutes() {
  const { user, passwordResetRequired } = useAuth();

  return (
    <>
      {/* Password change modal — shown when first login requires reset */}
      {user && passwordResetRequired && <PasswordChangeModal />}

      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
        <Route path="/" element={<Layout />}>
          {/* Everyone gets My Dashboard */}
          <Route index element={
            <RoleGuard allowedRoles={['EMPLOYEE', 'MANAGER', 'ADMIN']}>
              <EmployeeDashboard />
            </RoleGuard>
          } />
          <Route path="team" element={
            <RoleGuard allowedRoles={['MANAGER', 'ADMIN']}>
              <ManagerDashboard />
            </RoleGuard>
          } />
          <Route path="admin" element={
            <RoleGuard allowedRoles={['ADMIN']}>
              <AdminPanel />
            </RoleGuard>
          } />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
