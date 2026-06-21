import { useEffect, useState } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"
import { checkBackendHealth } from "@/lib/api"
import { isLiveDeployment } from "@/lib/apiConfig"
import { Button } from "@/components/ui/button"

export default function BackendStatusBanner() {
  const [online, setOnline] = useState(true)
  const [checking, setChecking] = useState(false)
  const [, setFailCount] = useState(0)

  const ping = async () => {
    setChecking(true)
    const health = await checkBackendHealth()
    if (health.ok) {
      setFailCount(0)
      setOnline(true)
    } else {
      setFailCount((c) => {
        const next = c + 1
        // Bot scan can make one slow response — need several misses before showing offline
        if (next >= 5) setOnline(false)
        return next
      })
    }
    setChecking(false)
  }

  useEffect(() => {
    ping()
    const id = setInterval(ping, 8000)
    return () => clearInterval(id)
  }, [])

  if (online) return null

  return (
    <div className="mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
      <div className="flex items-start gap-2 text-destructive">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
        <div>
          <p className="font-semibold">Backend not connected</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {isLiveDeployment
              ? "Cannot reach the backend server. It may still be starting — wait 30–60 seconds and click Retry."
              : "Start the local backend on port 8000, then click Retry."}
          </p>
        </div>
      </div>
      <Button variant="outline" size="sm" onClick={ping} disabled={checking} className="shrink-0">
        <RefreshCw className={`h-3.5 w-3.5 ${checking ? "animate-spin" : ""}`} />
        Retry
      </Button>
    </div>
  )
}
