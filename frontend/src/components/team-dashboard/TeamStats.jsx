import { Users, UserCheck, UserX, Clock, Activity } from "lucide-react";
import StatCard from "../dashboard/StatCard";

function asNumber(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export default function TeamStats({ stats }) {
  const s = stats && typeof stats === "object" ? stats : {};

  const teamMembers = asNumber(s.team_members ?? s.total_employees ?? s.totalMembers ?? 0, 0);
  const present = asNumber(s.present ?? s.total_present ?? 0, 0);
  const absent = asNumber(s.absent ?? s.total_absent ?? 0, 0);
  const late = asNumber(s.late ?? s.total_late ?? 0, 0);

  // Team Members Present = PRESENT + LATE (backend provides this, fallback to sum)
  const teamMembersPresent = asNumber(s.team_members_present ?? (present + late), 0);

  const attendanceRateRaw =
    s.attendance_rate ?? s.attendanceRate ?? (teamMembers > 0 ? (100 * teamMembersPresent) / teamMembers : 0);
  const attendanceRate = asNumber(attendanceRateRaw, 0);

  // Percentage for "Team Members Present" card: (PRESENT + LATE) / team_members
  const presentPct = teamMembers > 0 ? (100 * teamMembersPresent) / teamMembers : null;
  const absentPct = teamMembers > 0 ? (100 * absent) / teamMembers : null;
  const latePct = teamMembers > 0 ? (100 * late) / teamMembers : null;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <StatCard
        title="Team Members"
        value={teamMembers}
        subtitle="Total employees"
        icon={Users}
      />
      <StatCard
        title="Team Members Present"
        value={teamMembersPresent}
        subtitle={presentPct != null ? `${presentPct.toFixed(1)}% of team` : undefined}
        icon={UserCheck}
        valueClassName="text-emerald-600"
      />
      <StatCard
        title="Absent"
        value={absent}
        subtitle={absentPct != null ? `${absentPct.toFixed(1)}% of team` : undefined}
        icon={UserX}
        valueClassName="text-rose-600"
      />
      <StatCard
        title="Late"
        value={late}
        subtitle={latePct != null ? `${latePct.toFixed(1)}% of team` : undefined}
        icon={Clock}
        valueClassName="text-amber-600"
      />
      <StatCard
        title="Attendance Rate"
        value={`${attendanceRate.toFixed(1)}%`}
        subtitle="Average attendance"
        icon={Activity}
        valueClassName="text-primary"
      />
    </div>
  );
}
