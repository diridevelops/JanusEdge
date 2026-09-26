import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { WorkspaceModeGuard } from './components/layout/WorkspaceModeGuard';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { ToastContainer } from './components/ui/Toast';
import { AuthProvider } from './contexts/AuthContext';
import { ClientConfigProvider } from './contexts/ClientConfigContext';
import { FilterProvider } from './contexts/FilterContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ToastProvider } from './contexts/ToastContext';
import { WorkspaceModeProvider } from './contexts/WorkspaceModeContext';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { BacktestRunListPage } from './pages/BacktestRunListPage';
import { CalendarPage } from './pages/CalendarPage';
import { DashboardPage } from './pages/DashboardPage';
import { ImportPage } from './pages/ImportPage';
import { LoginPage } from './pages/LoginPage';
import { ManualTradePage } from './pages/ManualTradePage';
import { MarketDataImportPage } from './pages/MarketDataImportPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { RegisterPage } from './pages/RegisterPage';
import { SettingsPage } from './pages/SettingsPage';
import { TradeDetailPage } from './pages/TradeDetailPage';
import { TradeListPage } from './pages/TradeListPage';
import { WhatIfPage } from './pages/WhatIfPage';
import { Spinner } from './components/ui/Spinner';

const BacktestReplayPage = lazy(() => import('./pages/BacktestReplayPage').then(
  ({ BacktestReplayPage: page }) => ({ default: page })
));

/** Root application component with routing and context providers. */
export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ClientConfigProvider>
          <AuthProvider>
            <FilterProvider>
              <ToastProvider>
                <WorkspaceModeProvider>
                  <ErrorBoundary>
                    <Routes>
                      {/* Public routes */}
                      <Route path="/login" element={<LoginPage />} />
                      <Route path="/register" element={<RegisterPage />} />

                      {/* Protected routes with layout */}
                      <Route
                        element={(
                          <ProtectedRoute>
                            <AppLayout />
                          </ProtectedRoute>
                        )}
                      >
                        <Route path="/" element={<DashboardPage />} />
                        <Route path="/trades" element={<TradeListPage />} />
                        <Route path="/trades/:id" element={<TradeDetailPage />} />
                        <Route
                          path="/import"
                          element={(
                            <WorkspaceModeGuard requiredMode="real">
                              <ImportPage />
                            </WorkspaceModeGuard>
                          )}
                        />
                        <Route
                          path="/trades/new"
                          element={(
                            <WorkspaceModeGuard requiredMode="real">
                              <ManualTradePage />
                            </WorkspaceModeGuard>
                          )}
                        />
                        <Route path="/market-data/import" element={<MarketDataImportPage />} />
                        <Route path="/analytics" element={<AnalyticsPage />} />
                        <Route path="/calendar" element={<CalendarPage />} />
                        <Route path="/whatif" element={<WhatIfPage />} />
                        <Route path="/settings" element={<SettingsPage />} />
                        <Route
                          path="/backtest"
                          element={(
                            <WorkspaceModeGuard requiredMode="backtest">
                              <Navigate to="/backtest/runs" replace />
                            </WorkspaceModeGuard>
                          )}
                        />
                        <Route
                          path="/backtest/runs"
                          element={(
                            <WorkspaceModeGuard requiredMode="backtest">
                              <BacktestRunListPage />
                            </WorkspaceModeGuard>
                          )}
                        />
                        <Route
                          path="/backtest/runs/:runId/replay"
                          element={(
                            <WorkspaceModeGuard requiredMode="backtest">
                              <Suspense fallback={(
                                <div className="flex min-h-64 items-center justify-center" aria-label="Loading replay">
                                  <Spinner />
                                </div>
                              )}>
                                <BacktestReplayPage />
                              </Suspense>
                            </WorkspaceModeGuard>
                          )}
                        />
                      </Route>

                      {/* Catch-all */}
                      <Route path="*" element={<NotFoundPage />} />
                    </Routes>
                  </ErrorBoundary>
                </WorkspaceModeProvider>
                <ToastContainer />
              </ToastProvider>
            </FilterProvider>
          </AuthProvider>
        </ClientConfigProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
