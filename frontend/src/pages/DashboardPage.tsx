import { Car, Bell, Filter, Activity, Clock, ChevronRight, RefreshCw } from "lucide-react"
import { Link } from "react-router-dom"
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts"
import { useMonitoring } from "@/contexts/MonitoringContext"
import { getDashboardCharts } from "@/lib/api"
import type { DashboardCharts } from "@/types"
import { useEffect, useState } from "react"
import { StatCard } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/badge"
import { formatDate, formatIntervalRange, normalizeIntervalBounds, DEFAULT_SCAN_MIN_SECONDS, DEFAULT_SCAN_MAX_SECONDS } from "@/lib/utils"
import { cn } from "@/lib/utils"

function InfoCard({ to, icon: Icon, label, value, iconClass }: {
  to: string
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number
  iconClass?: string
}) {
  return (
    <Link to={to}>
      <Card className="border-[#1877F2]/10 hover:shadow-md hover:border-[#1877F2]/30 transition-all cursor-pointer group">
        <CardContent className="p-5 flex items-center gap-4">
          <div className={cn("h-11 w-11 rounded-xl flex items-center justify-center", iconClass || "bg-muted")}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">{label}</p>
            <p className="text-sm font-semibold mt-0.5">{value}</p>
          </div>
          <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        </CardContent>
      </Card>
    </Link>
  )
}

export default function DashboardPage() {
  const { stats, settings, loading } = useMonitoring()
  const [charts, setCharts] = useState<DashboardCharts | null>(null)

  useEffect(() => {
    getDashboardCharts().then(({ data }) => setCharts(data))
  }, [])

  if (loading && !stats) {
    return <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>
  }

  const { min: minSec, max: maxSec } = normalizeIntervalBounds(
    settings?.refresh_interval_min_seconds ?? DEFAULT_SCAN_MIN_SECONDS,
    settings?.refresh_interval_max_seconds ?? DEFAULT_SCAN_MAX_SECONDS,
  )

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground text-sm mt-1">Click any card to view details</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard title="Matched Listings" value={stats?.total_listings ?? 0} icon={Car} to="/listings" />
        <StatCard title="Today" value={stats?.today_listings ?? 0} icon={Activity} to="/listings?today=1" />
        <StatCard title="Emails Sent" value={stats?.notifications_sent ?? 0} icon={Bell} to="/notifications" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <InfoCard
          to="/filters"
          icon={Filter}
          label="Active Filters"
          value={stats?.active_filters ?? 0}
          iconClass="bg-[#1877F2]/10 text-[#1877F2]"
        />
        <InfoCard
          to="/monitoring"
          icon={Clock}
          label="Last check"
          value={stats?.last_scan_at ? formatDate(stats.last_scan_at) : "Never"}
          iconClass="bg-muted text-muted-foreground"
        />
        <InfoCard
          to="/monitoring"
          icon={RefreshCw}
          label="Check every"
          value={formatIntervalRange(minSec, maxSec)}
          iconClass="bg-[#1877F2]/10 text-[#1877F2]"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Link to="/listings">
          <Card className="hover:shadow-md hover:border-[#1877F2]/20 transition-all cursor-pointer h-full">
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-base">Listings Found Per Day</CardTitle>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={charts?.listings_per_day ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)" }} />
                  <Area type="monotone" dataKey="count" stroke="#1877F2" fill="#1877F2" fillOpacity={0.12} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Link>

        <Link to="/listings">
          <Card className="hover:shadow-md hover:border-[#1877F2]/20 transition-all cursor-pointer h-full">
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-base">Matches Per Day</CardTitle>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={charts?.matches_per_day ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)" }} />
                  <Bar dataKey="count" fill="#1877F2" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Link>

        <Link to="/notifications" className="lg:col-span-2">
          <Card className="hover:shadow-md hover:border-emerald-500/20 transition-all cursor-pointer">
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-base">Notifications Sent Per Day</CardTitle>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={charts?.notifications_per_day ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)" }} />
                  <Area type="monotone" dataKey="count" stroke="#22C55E" fill="#22C55E" fillOpacity={0.12} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  )
}
