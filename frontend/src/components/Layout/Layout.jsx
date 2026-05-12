import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { LayoutDashboard, Users, Upload, LogOut, Sun, Moon } from 'lucide-react';
import { cn } from '../../lib/utils';
import { memo } from 'react';
import { prefetchCache } from '../../lib/cache';
import { useTheme } from '../../lib/ThemeProvider';
import api from '../../api/client';

// ── Prefetch functions (called on sidebar hover) ──────
function prefetchEmployeeDashboard() {
  prefetchCache('employee-dashboard-v4', async () => {
    const res = await api.get('/attendance/me/dashboard');
    return res?.data ?? null;
  });
}

function prefetchTeamDashboard() {
  prefetchCache('team-dashboard-v2', async () => {
    const now = new Date();
    const res = await api.get('/attendance/team/dashboard', {
      params: {
        target_date: now.toISOString().slice(0, 10),
        month: now.getMonth() + 1,
        year: now.getFullYear(),
      },
    });
    const dashboardData = res?.data ?? {};
    return {
      dashboard: dashboardData,
      monthly: { records: dashboardData.members ?? [] },
    };
  });
}

// ── Nav link styling helper ──────────────────────────
function navCls({ isActive }) {
  return cn(
    "flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] font-medium transition-all duration-150 relative",
    isActive
      ? "bg-primary/10 text-primary font-semibold shadow-[inset_2.5px_0_0_0] shadow-primary"
      : "text-muted-foreground hover:bg-muted hover:text-foreground"
  );
}

// ── Memoized Sidebar ──────────────────────────────────
const Sidebar = memo(function Sidebar({ user, logout, isManager, isAdmin }) {
  const initials =
    typeof user?.full_name === "string"
      ? user.full_name
          .split(" ")
          .filter(Boolean)
          .map((n) => n[0])
          .join("")
          .slice(0, 2)
          .toUpperCase()
      : "??";

  return (
    <aside className="fixed inset-y-0 left-0 w-[var(--sidebar-width)] flex flex-col border-r border-border bg-secondary z-50 transition-colors duration-200">
      {/* Text Branding */}
      <div className="flex items-center px-4 py-3 border-b border-border">
        <span className="text-lg font-bold tracking-tight text-foreground">
          <span className="text-primary">A</span>TRACK
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-0.5 px-3 py-2">
        <NavLink to="/" end onMouseEnter={prefetchEmployeeDashboard} className={navCls}>
          <LayoutDashboard size={15} className="shrink-0" /> My Dashboard
        </NavLink>

        {isManager && (
          <NavLink to="/team" onMouseEnter={prefetchTeamDashboard} className={navCls}>
            <Users size={15} className="shrink-0" /> Team View
          </NavLink>
        )}

        {isAdmin && (
          <NavLink to="/admin" className={navCls}>
            <Upload size={15} className="shrink-0" /> Admin Panel
          </NavLink>
        )}
      </nav>

      {/* Footer / User Profile */}
      <div className="mx-3 mb-2 p-2 border border-border bg-card/50 rounded-lg transition-colors duration-200">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-muted border border-border flex items-center justify-center font-bold text-[9px] text-foreground shrink-0 tracking-wide">
            {initials}
          </div>
          <div className="overflow-hidden flex-1 min-w-0">
            <div className="text-[11px] font-semibold text-foreground truncate leading-tight">
              {user?.full_name}
            </div>
            <div className="text-[9px] text-muted-foreground uppercase tracking-wider font-medium leading-tight">
              {user?.role} • {user?.department}
            </div>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-1.5 w-full text-[10px] text-muted-foreground mt-1.5 pt-1.5 border-t border-border rounded-sm hover:text-rose-500 transition-colors"
        >
          <LogOut size={11} /> Sign Out
        </button>
      </div>
    </aside>
  );
});

// ── Theme Toggle Button ───────────────────────────────
function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      className="inline-flex items-center justify-center rounded-lg border border-border bg-card p-1.5 shadow-sm transition-all duration-200 hover:shadow-md hover:scale-105"
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
    >
      {theme === 'dark' ? (
        <Sun className="h-3.5 w-3.5 text-amber-400 transition-transform duration-200" />
      ) : (
        <Moon className="h-3.5 w-3.5 text-muted-foreground transition-transform duration-200" />
      )}
    </button>
  );
}

export default function Layout() {
  const { user, logout, isManager, isAdmin } = useAuth();

  return (
    <div className="flex min-h-screen relative z-10 bg-background text-foreground transition-colors duration-200">
      <Sidebar user={user} logout={logout} isManager={isManager} isAdmin={isAdmin} />

      {/* Main Content Area */}
      <main className="ml-[var(--sidebar-width)] flex-1 p-6 max-w-[1400px]">
        {/* Global theme toggle */}
        <div className="flex justify-end mb-3">
          <ThemeToggle />
        </div>
        <Outlet />
      </main>
    </div>
  );
}
