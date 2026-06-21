import axios from "axios"
import { getApiBaseUrl, getHealthUrl, isLiveDeployment } from "@/lib/apiConfig"

const api = axios.create({
  baseURL: getApiBaseUrl(),
  headers: { "Content-Type": "application/json" },
  timeout: 45000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const isLoginRequest = error.config?.url?.includes("/auth/login")
      if (!isLoginRequest) {
        localStorage.removeItem("token")
        if (!window.location.pathname.includes("/login")) {
          window.location.href = "/login"
        }
      }
    }
    return Promise.reject(error)
  }
)

export default api

export async function checkBackendHealth(): Promise<{ ok: boolean; status: string; database: string; ready?: boolean }> {
  const timeoutMs = isLiveDeployment ? 60000 : 5000
  try {
    const res = await axios.get(getHealthUrl(), { timeout: timeoutMs })
    const status = res.data?.status ?? "unknown"
    const database = res.data?.database ?? "unknown"
    const ready = Boolean(res.data?.ready)
    return {
      ok: ready || status === "healthy",
      status,
      database,
      ready,
    }
  } catch {
    return { ok: false, status: "offline", database: "offline", ready: false }
  }
}

export function loginErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      if (isLiveDeployment) {
        return "Cannot reach the backend — the server may still be starting. Wait 30 seconds and try again."
      }
      return "Backend not reachable — start the backend on port 8000, then try again."
    }
    const detail = error.response.data?.detail
    if (typeof detail === "string") return detail
    if (error.response.status === 503) {
      return "Database still connecting — wait 30 seconds and try again."
    }
    if (error.response.status === 401) {
      return "Invalid email or password — use ADMIN_EMAIL and ADMIN_PASSWORD from backend .env"
    }
  }
  return "Login failed — try again."
}

// Auth
export const login = (email: string, password: string) =>
  api.post("/auth/login", { email, password }, { timeout: 20000 })

export const getMe = () => api.get("/auth/me")
export const updateProfile = (data: { full_name?: string; email?: string }) =>
  api.put("/auth/profile", data)
export const changePassword = (current_password: string, new_password: string) =>
  api.post("/auth/change-password", { current_password, new_password })

// Dashboard
export const getDashboardStats = () => api.get("/dashboard/stats")
export const getDashboardCharts = () => api.get("/dashboard/charts")

// Monitoring
export const getMonitoringSettings = () => api.get("/monitoring/settings")
export const updateMonitoringSettings = (data: {
  is_enabled?: boolean
  refresh_interval_min_seconds?: number
  refresh_interval_max_seconds?: number
}) => api.put("/monitoring/settings", data)
export const startBot = () => api.post("/monitoring/start", {}, { timeout: 30000 })
export const stopBot = () => api.post("/monitoring/stop", {}, { timeout: 30000 })

// Filters
export const getFilters = () => api.get("/filters")
export const getFilter = (id: number) => api.get(`/filters/${id}`)
export const createFilter = (data: Record<string, unknown>) => api.post("/filters", data)
export const updateFilter = (id: number, data: Record<string, unknown>) => api.put(`/filters/${id}`, data)
export const deleteFilter = (id: number) => api.delete(`/filters/${id}`)

// Templates
export const getTemplates = () => api.get("/filter-templates")
export const createTemplate = (name: string, filter_data: Record<string, unknown>) =>
  api.post("/filter-templates", { name, filter_data })
export const loadTemplate = (id: number) => api.post(`/filter-templates/${id}/load`)
export const duplicateTemplate = (id: number) => api.post(`/filter-templates/${id}/duplicate`)
export const deleteTemplate = (id: number) => api.delete(`/filter-templates/${id}`)

// Listings
export const getListings = (params: Record<string, unknown>) => api.get("/listings", { params })
export const getListing = (id: number) => api.get(`/listings/${id}`)
export const exportListings = () => api.get("/listings/export/csv", { responseType: "blob" })
export const deleteListings = (ids: number[]) => api.delete("/listings", { data: { ids } })
export const deleteAllListings = () => api.delete("/listings/all")

// Notifications
export const getNotifications = (params: Record<string, unknown>) => api.get("/notifications", { params })
export const getRecipients = () => api.get("/notification-recipients")
export const addRecipient = (data: { email: string; name?: string; is_active?: boolean }) =>
  api.post("/notification-recipients", data)
export const updateRecipient = (id: number, data: { email: string; name?: string; is_active?: boolean }) =>
  api.put(`/notification-recipients/${id}`, data)
export const deleteRecipient = (id: number) => api.delete(`/notification-recipients/${id}`)
export const sendTestEmail = (email?: string) =>
  api.post("/notifications/test-email", email ? { email } : {})
export const sendTestLoginReminder = () => api.post("/notifications/test-login-reminder")

// Settings & Logs
export const getSettings = () => api.get("/settings")
export const updateSettings = (settings: Record<string, string>) => api.put("/settings", { settings })
export const clearBrowserSession = () => api.post("/settings/clear-browser-session")
export const getLogs = (params: Record<string, unknown>) => api.get("/logs", { params })
export const exportLogs = () => api.get("/logs/export/csv", { responseType: "blob" })
export const deleteLogs = (ids: number[]) => api.delete("/logs", { data: { ids } })
export const deleteAllLogs = () => api.delete("/logs/all")
