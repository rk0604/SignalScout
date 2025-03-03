import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import RegisterPage, { LoginPage } from "./components/auth_components/register";
import Dashboard from "./components/dashboard/DashboardPage";
import StockProvider from "./components/StockContext";

function RootApp() {
  return (
    <Router>
      <div className="parent-container">
        <StockProvider>
          <Routes>
            <Route path="/" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/dashboard" element={<Dashboard />} />
          </Routes>
        </StockProvider>
      </div>
    </Router>
  );
}

export default RootApp;
