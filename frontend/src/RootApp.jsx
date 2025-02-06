import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import RegisterPage, { LoginPage } from "./components/auth_components/register";
import Dashboard from "./components/dashboard/DashboardPage";

function RootApp() {
  return (
    <Router>
      <div className="parent-container">
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </div>
    </Router>
  );
}

export default RootApp;
