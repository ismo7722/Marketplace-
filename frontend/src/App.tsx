import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { AuthProvider } from "@/contexts/AuthContext"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { ToastProvider } from "@/contexts/ToastContext"
import { MonitoringProvider } from "@/contexts/MonitoringContext"
import ProtectedRoute from "@/components/layout/ProtectedRoute"
import DashboardLayout from "@/components/layout/DashboardLayout"
import LoginPage from "@/pages/LoginPage"
import DashboardPage from "@/pages/DashboardPage"
import FiltersPage from "@/pages/FiltersPage"
import ListingsPage from "@/pages/ListingsPage"
import ListingDetailPage from "@/pages/ListingDetailPage"
import MonitoringPage from "@/pages/MonitoringPage"
import NotificationsPage from "@/pages/NotificationsPage"
import LogsPage from "@/pages/LogsPage"
import SettingsPage from "@/pages/SettingsPage"
import HelpPage from "@/pages/HelpPage"

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/" element={
                <ProtectedRoute>
                  <MonitoringProvider>
                    <DashboardLayout />
                  </MonitoringProvider>
                </ProtectedRoute>
              }>
                <Route index element={<DashboardPage />} />
                <Route path="filters" element={<FiltersPage />} />
                <Route path="listings" element={<ListingsPage />} />
                <Route path="listings/:id" element={<ListingDetailPage />} />
                <Route path="monitoring" element={<MonitoringPage />} />
                <Route path="notifications" element={<NotificationsPage />} />
                <Route path="logs" element={<LogsPage />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="help" element={<HelpPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
