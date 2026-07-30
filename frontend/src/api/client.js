import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL;

const TOKEN_KEY = "token";
const EMAIL_KEY = "email";

// ---------------------------------------------- token helpers ----------------------------------------------

export const getToken = () => localStorage.getItem(TOKEN_KEY);

export const setSession = (token, email) => {
  localStorage.setItem(TOKEN_KEY, token);
  if (email) localStorage.setItem(EMAIL_KEY, email);
};

export const clearSession = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
  // Drop the realtime socket too, otherwise an authenticated connection
  // outlives the session that created it. Imported lazily to avoid a cycle
  // (realtime.js reads getToken from this module).
  import("./realtime")
    .then((m) => m.disconnectRealtime())
    .catch(() => {});
};

export const isLoggedIn = () => Boolean(getToken());

// ---------------------------------------------- axios instance ----------------------------------------------

const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: { Accept: "application/json" },
});

// Attach the bearer token to every outgoing request. Components no longer pass
// an email around — the backend derives identity from this token.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// A 401 means the token is missing/expired/invalid: drop the session and send
// the user back to the login page.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearSession();
      if (window.location.pathname !== "/") {
        window.location.replace("/");
      }
    }
    return Promise.reject(error);
  }
);

export default api;
