import { NavLink, Outlet, useNavigate, Navigate } from "react-router-dom";
import PropTypes from "prop-types";
import { clearSession, isLoggedIn } from "../../api/client";
import "./shell.css";

/*
 * Application shell: persistent top navigation plus the routed page body.
 *
 * The features used to be stacked on one dashboard, which is why it felt
 * crowded. Each now gets its own route, and the nav is the only thing that
 * persists.
 */

const NAV = [
  { to: "/app/overview", label: "Overview" },
  { to: "/app/research", label: "Research" },
  { to: "/app/backtest", label: "Backtest" },
  { to: "/app/agent", label: "Agent" },
  { to: "/app/activity", label: "Activity" },
];

export function RequireAuth({ children }) {
  // Previously any visitor could load the dashboard and see an empty shell
  // until the first 401 bounced them. Gate it up front instead.
  if (!isLoggedIn()) return <Navigate to="/" replace />;
  return children;
}

RequireAuth.propTypes = { children: PropTypes.node };

export default function AppShell() {
  const navigate = useNavigate();
  const email = localStorage.getItem("email") || "";

  const signOut = () => {
    clearSession();
    navigate("/", { replace: true });
  };

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true" />
            <span className="brand-name">SignalScout</span>
          </div>

          <nav className="nav" aria-label="Main">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `nav-link${isActive ? " is-active" : ""}`}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="topbar-right">
            <span className="user-email" title={email}>{email}</span>
            <button className="btn btn-ghost btn-sm" onClick={signOut}>Sign out</button>
          </div>
        </div>
      </header>

      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}
