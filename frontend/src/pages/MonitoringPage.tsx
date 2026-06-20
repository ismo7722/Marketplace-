import { useEffect, useState } from "react"
import { RefreshCw, Clock } from "lucide-react"
import { getMonitoringSettings, updateMonitoringSettings } from "@/lib/api"
import type { MonitoringSettings } from "@/types"
import { Button } from "@/components/ui/button"
import { Input, Label } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge, Spinner } from "@/components/ui/badge"
import { useToast } from "@/contexts/ToastContext"
import { SCAN_DELAY_PRESETS, formatDate, formatIntervalRange } from "@/lib/utils"

const DEFAULT_MIN = 30
const DEFAULT_MAX = 45

export default function MonitoringPage() {
  const [settings, setSettings] = useState<MonitoringSettings | null>(null)
  const [minSeconds, setMinSeconds] = useState(String(DEFAULT_MIN))
  const [maxSeconds, setMaxSeconds] = useState(String(DEFAULT_MAX))
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await getMonitoringSettings()
      setSettings(data)
      setMinSeconds(String(data.refresh_interval_min_seconds || DEFAULT_MIN))
      setMaxSeconds(String(data.refresh_interval_max_seconds || DEFAULT_MAX))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const save = async (updates: Parameters<typeof updateMonitoringSettings>[0]) => {
    setSaving(true)
    try {
      const { data } = await updateMonitoringSettings(updates)
      setSettings(data)
      setMinSeconds(String(data.refresh_interval_min_seconds || DEFAULT_MIN))
      setMaxSeconds(String(data.refresh_interval_max_seconds || DEFAULT_MAX))
      toast("Monitoring interval saved", "success")
    } catch {
      toast("Failed to save settings", "error")
    } finally {
      setSaving(false)
    }
  }

  const saveDelayRange = async (minSec: number, maxSec: number) => {
    if (minSec < 30) {
      toast("Minimum is 30 seconds", "warning")
      return
    }
    if (maxSec < minSec) {
      toast("Max seconds must be ≥ min seconds", "warning")
      return
    }
    await save({
      refresh_interval_min_seconds: minSec,
      refresh_interval_max_seconds: maxSec,
    })
  }

  const applyCustomRange = () => {
    const minSec = Math.round(Number(minSeconds))
    const maxSec = Math.round(Number(maxSeconds))
    if (!Number.isFinite(minSec) || !Number.isFinite(maxSec)) {
      toast("Enter valid numbers", "warning")
      return
    }
    saveDelayRange(minSec, maxSec)
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>

  const minSec = settings?.refresh_interval_min_seconds ?? DEFAULT_MIN
  const maxSec = settings?.refresh_interval_max_seconds ?? DEFAULT_MAX

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Monitoring</h1>
        <p className="text-muted-foreground text-sm mt-1">
          How often the bot refreshes listings and checks for matches. Start / Stop on Dashboard.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Status</CardTitle>
            <CardDescription>Start / Stop on Dashboard</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
              <div className={`h-3 w-3 rounded-full shrink-0 ${settings?.is_enabled ? "bg-success animate-pulse" : "bg-muted-foreground"}`} />
              <span className="text-sm font-medium">
                {settings?.is_enabled
                  ? "ON — bot is running"
                  : "OFF — press Start on Dashboard"}
              </span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
              <span>
                Last check:{" "}
                <strong>{settings?.last_scan_at ? formatDate(settings.last_scan_at) : "Never"}</strong>
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Current check interval</CardTitle>
            <CardDescription>Random wait between listing refreshes on /vehicles</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
              <RefreshCw className="h-5 w-5 text-[#1877F2] shrink-0" />
              <div>
                <p className="text-2xl font-bold tabular-nums">{formatIntervalRange(minSec, maxSec)}</p>
                <p className="text-xs text-muted-foreground mt-1">Minimum 30 seconds each value</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Listing check interval (seconds)</CardTitle>
          <CardDescription>
            After filters are applied once, the bot scrolls the Vehicles page, tries to match listings,
            then waits a random time in this range before refreshing the same page to look for new listings.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {SCAN_DELAY_PRESETS.map((opt) => {
              const active = minSec === opt.min && maxSec === opt.max
              return (
                <Button
                  key={opt.label}
                  variant={active ? "default" : "outline"}
                  size="sm"
                  onClick={() => saveDelayRange(opt.min, opt.max)}
                  disabled={saving}
                >
                  {opt.label}
                </Button>
              )
            })}
          </div>

          <div className="flex flex-col sm:flex-row items-end gap-3 pt-4 border-t border-border">
            <div className="space-y-2 flex-1">
              <Label>Min seconds</Label>
              <Input type="number" min={30} step={1} value={minSeconds} onChange={(e) => setMinSeconds(e.target.value)} />
            </div>
            <div className="space-y-2 flex-1">
              <Label>Max seconds</Label>
              <Input type="number" min={30} step={1} value={maxSeconds} onChange={(e) => setMaxSeconds(e.target.value)} />
            </div>
            <Button variant="secondary" onClick={applyCustomRange} disabled={saving}>
              Save interval
            </Button>
          </div>

          <p className="text-sm text-muted-foreground">
            Active:{" "}
            <Badge variant="secondary">{formatIntervalRange(minSec, maxSec)}</Badge>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
