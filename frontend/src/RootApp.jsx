import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import RegisterPage, { LoginPage } from "./components/auth_components/register";
import AppShell, { RequireAuth } from "./components/layout/AppShell";
import OverviewPage from "./pages/OverviewPage";
import ResearchPage from "./pages/ResearchPage";
import BacktestPage from "./pages/BacktestPage";
import AgentPage from "./pages/AgentPage";
import ActivityPage from "./pages/ActivityPage";
import StockProvider from "./components/StockContext";

function RootApp() {
  return (
    <Router>
      <StockProvider>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* Everything under /app requires a session */}
          <Route
            path="/app"
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/app/overview" replace />} />
            <Route path="overview" element={<OverviewPage />} />
            <Route path="research" element={<ResearchPage />} />
            <Route path="backtest" element={<BacktestPage />} />
            <Route path="agent" element={<AgentPage />} />
            <Route path="activity" element={<ActivityPage />} />
          </Route>

          {/* Old bookmark from the single-dashboard layout */}
          <Route path="/dashboard" element={<Navigate to="/app/overview" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </StockProvider>
    </Router>
  );
}

export default RootApp;
