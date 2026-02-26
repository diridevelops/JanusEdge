import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { ToastContainer } from './components/ui/Toast';
import { AuthProvider } from './contexts/AuthContext';
import { FilterProvider } from './contexts/FilterContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ToastProvider } from './contexts/ToastContext';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { CalendarPage } from './pages/CalendarPage';
import { DashboardPage } from './pages/DashboardPage';
import { ImportPage } from './pages/ImportPage';
import { LoginPage } from './pages/LoginPage';
import { ManualTradePage } from './pages/ManualTradePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { RegisterPage } from './pages/RegisterPage';
import { SettingsPage } from './pages/SettingsPage';
import { TradeDetailPage } from './pages/TradeDetailPage';
import { TradeListPage } from './pages/TradeListPage';

/**
 * Root application component with routing and context providers.
 */
export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <FilterProvider>
            <ToastProvider>
              <ErrorBoundary>
                <Routes>
                  {/* Public routes */}
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/register" element={<RegisterPage />} />

                  {/* Protected routes with layout */}
                  <Route
                    element={
                      <ProtectedRoute>
                        <AppLayout />
                      </ProtectedRoute>
                    }
                  >
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/trades" element={<TradeListPage />} />
                    <Route path="/trades/new" element={<ManualTradePage />} />
                    <Route path="/trades/:id" element={<TradeDetailPage />} />
                    <Route path="/import" element={<ImportPage />} />
                    <Route path="/analytics" element={<AnalyticsPage />} />
                    <Route path="/calendar" element={<CalendarPage />} />
                    <Route path="/settings" element={<SettingsPage />} />
                  </Route>

                  {/* Catch-all */}
                  <Route path="*" element={<NotFoundPage />} />
                </Routes>
              </ErrorBoundary>
              <ToastContainer />
            </ToastProvider>
          </FilterProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
