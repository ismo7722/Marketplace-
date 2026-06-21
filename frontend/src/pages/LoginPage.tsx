import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Eye, EyeOff } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/contexts/ToastContext"
import { Logo } from "@/components/brand/Logo"
import { Button } from "@/components/ui/button"
import { Input, Label } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/badge"
import { checkBackendHealth, loginErrorMessage } from "@/lib/api"
import { cn } from "@/lib/utils"

export default function LoginPage() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [backendStatus, setBackendStatus] = useState<"checking" | "ready" | "connecting" | "offline">("checking")
  const { login } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()

  const canSubmit = backendStatus === "ready" && email.trim() && password

  useEffect(() => {
    let cancelled = false
    let attempts = 0

    const poll = async () => {
      const health = await checkBackendHealth()
      if (cancelled) return

      if (health.ok) {
        setBackendStatus("ready")
        return
      }
      if (health.status === "starting" || health.database === "connecting") {
        setBackendStatus("connecting")
      } else if (attempts === 0) {
        setBackendStatus("checking")
      } else {
        setBackendStatus(attempts < 25 ? "connecting" : "offline")
      }

      attempts += 1
      if (attempts < 30 && !health.ok) {
        setTimeout(poll, 3000)
      }
    }

    poll()
    return () => {
      cancelled = true
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (backendStatus !== "ready") {
      toast("Backend not ready yet — wait a moment and try again", "warning")
      return
    }
    setLoading(true)
    try {
      await login(email.trim(), password)
      toast("Welcome back!", "success")
      navigate("/")
    } catch (err) {
      toast(loginErrorMessage(err), "error")
    } finally {
      setLoading(false)
    }
  }

  const statusMessage =
    backendStatus === "checking"
      ? "Connecting to server..."
      : backendStatus === "connecting"
        ? "Server is starting — first visit can take up to 60 seconds..."
        : backendStatus === "offline"
          ? "Cannot reach backend — wait and refresh, or try again in a minute"
          : "Enter your email and password to sign in"

  return (
    <div className="flex min-h-screen">
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-[#1877F2] to-[#0d5bbd] items-center justify-center p-12">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-20 left-20 w-72 h-72 bg-white rounded-full blur-3xl" />
          <div className="absolute bottom-20 right-20 w-96 h-96 bg-white rounded-full blur-3xl" />
        </div>
        <div className="relative text-center text-white max-w-md">
          <img src="/logo.svg" alt="Facebook Marketplace Monitor" className="h-24 w-24 rounded-3xl shadow-2xl mx-auto mb-8" />
          <h1 className="text-3xl font-bold mb-3">Facebook Marketplace Monitor</h1>
          <p className="text-blue-100 text-lg leading-relaxed">
            24/7 vehicle monitoring for Zurich. Get instant email alerts when matching listings appear.
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center bg-background p-6">
        <div className="w-full max-w-md animate-fade-in">
          <div className="flex flex-col items-center mb-8 lg:hidden">
            <Logo size={64} className="mb-4 shadow-md" />
            <h1 className="text-2xl font-bold">Facebook Marketplace Monitor</h1>
            <p className="text-muted-foreground text-sm mt-1">Vehicle Monitoring Dashboard</p>
          </div>

          <Card className="shadow-lg border-border/60">
            <CardHeader>
              <CardTitle>Sign In</CardTitle>
              <CardDescription>{statusMessage}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" placeholder="Enter your email" value={email} onChange={(e) => setEmail(e.target.value)} required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <Input id="password" type={showPassword ? "text" : "password"} placeholder="Enter your password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                    <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" onClick={() => setShowPassword(!showPassword)}>
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
                <Button
                  type="submit"
                  className={cn(
                    "w-full font-semibold transition-colors",
                    canSubmit
                      ? "bg-[#1877F2] hover:bg-[#166fe5] text-white"
                      : "bg-muted text-muted-foreground cursor-not-allowed"
                  )}
                  disabled={loading || !canSubmit}
                >
                  {loading ? <Spinner /> : backendStatus !== "ready" ? "Waiting for server..." : "Sign In to Dashboard"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
