import { useEffect, useState } from "react"
import { Shield, Bell, Send, Trash2, Plus, Monitor, Eraser, Clock } from "lucide-react"
import {
  getSettings, updateSettings, changePassword, clearBrowserSession,
  getRecipients, addRecipient, deleteRecipient, sendTestEmail, sendTestLoginReminder,
  getMonitoringSettings, updateMonitoringSettings,
} from "@/lib/api"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/contexts/ToastContext"
import { Button } from "@/components/ui/button"
import { Input, Label } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Badge, Spinner } from "@/components/ui/badge"
import { SCAN_DELAY_PRESETS, formatIntervalRange } from "@/lib/utils"

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [recipients, setRecipients] = useState<{ id: number; email: string; is_active: boolean }[]>([])
  const [alertEmail, setAlertEmail] = useState("")
  const [testEmail, setTestEmail] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [clearingSession, setClearingSession] = useState(false)
  const [sending, setSending] = useState(false)
  const [sendingReminder, setSendingReminder] = useState(false)
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [minSeconds, setMinSeconds] = useState("30")
  const [maxSeconds, setMaxSeconds] = useState("45")
  const [scanMinSec, setScanMinSec] = useState(30)
  const [scanMaxSec, setScanMaxSec] = useState(45)
  const { user } = useAuth()
  const { toast } = useToast()

  const load = async () => {
    const [settingsRes, recipientsRes, monitoringRes] = await Promise.all([
      getSettings(),
      getRecipients(),
      getMonitoringSettings(),
    ])
    setSettings(settingsRes.data)
    setRecipients(recipientsRes.data)
    const m = monitoringRes.data
    setScanMinSec(m.refresh_interval_min_seconds ?? 30)
    setScanMaxSec(m.refresh_interval_max_seconds ?? 45)
    setMinSeconds(String(m.refresh_interval_min_seconds || 30))
    setMaxSeconds(String(m.refresh_interval_max_seconds || 45))
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const notificationsEnabled = settings.notifications_enabled !== "false"
  const headlessMode = settings.playwright_headless !== "false"

  const handleToggleHeadless = async (headless: boolean) => {
    setSaving(true)
    try {
      await updateSettings({ playwright_headless: headless ? "true" : "false" })
      setSettings((prev) => ({ ...prev, playwright_headless: headless ? "true" : "false" }))
      toast(headless ? "Headless mode on — browser hidden during monitoring" : "Visible browser — Playwright Chromium opens on Start", "success")
    } catch {
      toast("Failed to save", "error")
    } finally {
      setSaving(false)
    }
  }

  const handleClearBrowserSession = async () => {
    if (!confirm("Close the browser and wipe all Facebook login data?\n\nNext Start will open a fresh Playwright Chromium window (like first time).")) {
      return
    }
    setClearingSession(true)
    try {
      await clearBrowserSession()
      toast("Browser closed and session wiped — next Start opens fresh Chromium", "success")
    } catch {
      toast("Failed to clear browser session", "error")
    } finally {
      setClearingSession(false)
    }
  }

  const handleToggleNotifications = async (enabled: boolean) => {
    setSaving(true)
    try {
      await updateSettings({ notifications_enabled: enabled ? "true" : "false" })
      setSettings((prev) => ({ ...prev, notifications_enabled: enabled ? "true" : "false" }))
      toast(enabled ? "Email alerts enabled" : "Email alerts disabled", "success")
    } catch {
      toast("Failed to save", "error")
    } finally {
      setSaving(false)
    }
  }

  const saveScanInterval = async (minSec: number, maxSec: number) => {
    if (minSec < 30) {
      toast("Minimum delay is 30 seconds", "warning")
      return
    }
    if (maxSec < minSec) {
      toast("Max must be greater than or equal to min", "warning")
      return
    }
    setSaving(true)
    try {
      const { data } = await updateMonitoringSettings({
        refresh_interval_min_seconds: minSec,
        refresh_interval_max_seconds: maxSec,
      })
      setScanMinSec(data.refresh_interval_min_seconds ?? minSec)
      setScanMaxSec(data.refresh_interval_max_seconds ?? maxSec)
        toast("Monitoring interval saved", "success")
    } catch {
      toast("Failed to save monitoring interval", "error")
    } finally {
      setSaving(false)
    }
  }

  const applyCustomScanInterval = () => {
    const minSec = Math.round(Number(minSeconds))
    const maxSec = Math.round(Number(maxSeconds))
    saveScanInterval(minSec, maxSec)
  }

  const handleAddAlertEmail = async () => {
    if (!alertEmail.trim()) return
    try {
      await addRecipient({ email: alertEmail.trim() })
      setAlertEmail("")
      toast("Alert email added", "success")
      load()
    } catch {
      toast("Failed to add email — may already exist", "error")
    }
  }

  const handleDeleteRecipient = async (id: number) => {
    await deleteRecipient(id)
    toast("Email removed", "success")
    load()
  }

  const handleTestEmail = async () => {
    const email = testEmail.trim() || recipients[0]?.email
    if (!email) {
      toast("Enter your email above, or add an alert recipient", "warning")
      return
    }
    setSending(true)
    try {
      await sendTestEmail(email)
      toast(`Test alert sent to ${email}`, "success")
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Failed — set SMTP_USER and SMTP_PASSWORD in backend .env"
      toast(msg, "error")
    } finally {
      setSending(false)
    }
  }

  const handleTestLoginReminder = async () => {
    setSendingReminder(true)
    try {
      await sendTestLoginReminder()
      toast("Login reminder test email sent", "success")
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Failed — configure SMTP in backend .env"
      toast(msg, "error")
    } finally {
      setSendingReminder(false)
    }
  }

  const handleChangePassword = async () => {
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword("")
      setNewPassword("")
      toast("Password changed successfully", "success")
    } catch {
      toast("Failed to change password", "error")
    }
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted-foreground text-sm mt-1">Alert emails, monitoring interval, browser, and account</p>
      </div>

      {/* Alert Email — user enters where to receive notifications */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-primary" />
            <CardTitle>Alert Email</CardTitle>
          </div>
          <CardDescription>Where to receive vehicle alerts</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-center justify-between p-4 rounded-lg border border-border bg-muted/30">
            <div>
              <p className="font-medium text-sm">Email Alerts</p>
            </div>
            <Switch
              checked={notificationsEnabled}
              onCheckedChange={handleToggleNotifications}
              disabled={saving}
            />
          </div>

          <div className="space-y-2">
            <Label>Your Alert Email</Label>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="your@email.com"
                value={alertEmail}
                onChange={(e) => setAlertEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddAlertEmail()}
              />
              <Button onClick={handleAddAlertEmail} disabled={!alertEmail.trim()}>
                <Plus className="h-4 w-4" /> Add
              </Button>
            </div>
          </div>

          {recipients.length > 0 && (
            <div className="space-y-2">
              <Label>Saved Alert Emails</Label>
              {recipients.map((r) => (
                <div key={r.id} className="flex items-center justify-between p-3 rounded-lg border border-border">
                  <span className="text-sm font-medium">{r.email}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-destructive"
                    onClick={() => handleDeleteRecipient(r.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}

          <div className="pt-4 border-t border-border space-y-3">
            <Label>Send Test Alert</Label>
            <p className="text-xs text-muted-foreground">
              Uses SMTP from backend .env (SMTP_USER, SMTP_PASSWORD). Enter your Gmail app password there, then test here.
            </p>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder={recipients[0]?.email || "your@email.com"}
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
              />
              <Button variant="outline" onClick={handleTestEmail} disabled={sending || sendingReminder}>
                {sending ? <Spinner /> : <><Send className="h-4 w-4" /> Test alert</>}
              </Button>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs"
              onClick={handleTestLoginReminder}
              disabled={sending || sendingReminder}
            >
              {sendingReminder ? <Spinner /> : "Test login reminder email (same as 5-min Facebook wait)"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-primary" />
            <CardTitle>Monitoring Interval</CardTitle>
          </div>
          <CardDescription>
            After each listings check, wait a random number of seconds in this range, then refresh the
            Vehicles page and scan again for new matches.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {SCAN_DELAY_PRESETS.map((opt) => {
              const active = scanMinSec === opt.min && scanMaxSec === opt.max
              return (
                <Button
                  key={opt.label}
                  variant={active ? "default" : "outline"}
                  size="sm"
                  onClick={() => saveScanInterval(opt.min, opt.max)}
                  disabled={saving}
                >
                  {opt.label}
                </Button>
              )
            })}
          </div>
          <div className="flex flex-col sm:flex-row items-end gap-3 pt-2 border-t border-border">
            <div className="space-y-2 flex-1">
              <Label>Min seconds</Label>
              <Input type="number" min={30} step={1} value={minSeconds} onChange={(e) => setMinSeconds(e.target.value)} />
            </div>
            <div className="space-y-2 flex-1">
              <Label>Max seconds</Label>
              <Input type="number" min={30} step={1} value={maxSeconds} onChange={(e) => setMaxSeconds(e.target.value)} />
            </div>
            <Button variant="secondary" onClick={applyCustomScanInterval} disabled={saving}>
              Save interval
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">
            Current:{" "}
            <Badge variant="secondary">
              {formatIntervalRange(scanMinSec, scanMaxSec)}
            </Badge>
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Monitor className="h-5 w-5 text-primary" />
            <CardTitle>Browser</CardTitle>
          </div>
          <CardDescription>Control how Facebook Marketplace opens during monitoring</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-4 rounded-lg border border-border bg-muted/30">
            <div>
              <p className="font-medium text-sm">Headless Mode</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {headlessMode
                  ? "Browser runs hidden (default, recommended for server)"
                  : "Playwright Chromium opens so you can see Facebook during monitoring"}
              </p>
            </div>
            <Switch
              checked={headlessMode}
              onCheckedChange={handleToggleHeadless}
              disabled={saving}
            />
          </div>
          <div className="flex items-center justify-between p-4 rounded-lg border border-border bg-muted/30">
            <div>
              <p className="font-medium text-sm">Clear browser (fresh start)</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Stops monitoring, closes Chromium, deletes session cookies. Next Start = fresh browser.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleClearBrowserSession}
              disabled={clearingSession}
            >
              {clearingSession ? <Spinner /> : <><Eraser className="h-4 w-4" /> Clear</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-primary" />
            <CardTitle>Change Password</CardTitle>
          </div>
          <CardDescription>Update your dashboard login password</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Current Password</Label>
            <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>New Password</Label>
            <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          </div>
          <Button onClick={handleChangePassword} disabled={!currentPassword || !newPassword}>
            Change Password
          </Button>
          <p className="text-xs text-muted-foreground">
            Logged in as {user?.email} ({user?.role})
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
