import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import PropTypes from "prop-types";
import api, { setSession, clearSession } from "../../api/client";

import "./auth_component_styles.css";

/* Shared chrome for both auth screens. */
function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-mark" aria-hidden="true" />
          <span className="auth-brand-name">SignalScout</span>
        </div>
        <h1 className="auth-title">{title}</h1>
        <p className="auth-sub">{subtitle}</p>
        {children}
        <div className="auth-footer">{footer}</div>
      </div>
      <p className="auth-note">
        Portfolio analytics with an auditable AI agent. Not financial advice.
      </p>
    </div>
  );
}

AuthLayout.propTypes = {
  title: PropTypes.string.isRequired,
  subtitle: PropTypes.string,
  children: PropTypes.node,
  footer: PropTypes.node,
};

// Register ------------------------------------------------------------------

const RegisterPage = () => {
  const navigate = useNavigate();
  const [formdata, setFormdata] = useState({ email: "", password: "", phone: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const handleChange = (e) =>
    setFormdata((prev) => ({ ...prev, [e.target.name]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await api.post("/register", formdata);
      if (response.status === 200) navigate("/", { replace: true });
    } catch (err) {
      const status = err.response?.status;
      setError(
        status === 400
          ? "Please fill in every field."
          : status === 500
          ? "That email or phone number is already registered."
          : "Could not create the account. Please try again."
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Track holdings, test strategies, and review agent proposals."
      footer={<>Already have an account? <Link to="/">Sign in</Link></>}
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        {error && <div className="alert alert-error">{error}</div>}

        <div className="auth-field">
          <label htmlFor="email">Email</label>
          <input className="field" type="email" id="email" name="email"
                 value={formdata.email} onChange={handleChange}
                 autoComplete="email" required />
        </div>

        <div className="auth-field">
          <label htmlFor="phone">Phone</label>
          <input className="field" type="tel" id="phone" name="phone"
                 value={formdata.phone} onChange={handleChange}
                 autoComplete="tel" required />
        </div>

        <div className="auth-field">
          <label htmlFor="password">Password</label>
          <input className="field" type="password" id="password" name="password"
                 value={formdata.password} onChange={handleChange}
                 autoComplete="new-password" required />
        </div>

        <button className="btn btn-primary auth-submit" type="submit" disabled={busy}>
          {busy ? "Creating account…" : "Create account"}
        </button>
      </form>
    </AuthLayout>
  );
};

// Login ---------------------------------------------------------------------

export function LoginPage() {
  const navigate = useNavigate();
  const [formdata, setFormdata] = useState({ email: "", password: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const handleChange = (e) =>
    setFormdata((prev) => ({ ...prev, [e.target.name]: e.target.value }));

  const handleLogin = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    clearSession(); // never leave a stale token behind on a failed attempt
    try {
      const response = await api.post("/login", formdata);
      if (response.status === 200 && response.data?.token) {
        setSession(response.data.token, response.data.email || formdata.email);
        navigate("/app/overview", { replace: true });
      }
    } catch (err) {
      const status = err.response?.status;
      setError(
        status === 400 || status === 404
          ? "Incorrect email or password."
          : "Could not sign in. Please try again."
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Welcome back."
      footer={<>New here? <Link to="/register">Create an account</Link></>}
    >
      <form className="auth-form" onSubmit={handleLogin}>
        {error && <div className="alert alert-error">{error}</div>}

        <div className="auth-field">
          <label htmlFor="login-email">Email</label>
          <input className="field" type="email" id="login-email" name="email"
                 value={formdata.email} onChange={handleChange}
                 autoComplete="email" required />
        </div>

        <div className="auth-field">
          <label htmlFor="login-password">Password</label>
          <input className="field" type="password" id="login-password" name="password"
                 value={formdata.password} onChange={handleChange}
                 autoComplete="current-password" required />
        </div>

        <button className="btn btn-primary auth-submit" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthLayout>
  );
}

export default RegisterPage;
