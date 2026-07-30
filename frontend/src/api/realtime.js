import { io } from "socket.io-client";
import { getToken } from "./client";

const API_URL = import.meta.env.VITE_API_URL;

/*
 * Realtime quote transport.
 *
 * One shared socket for the whole app: components subscribe to the tickers
 * they display and are called back when a new quote arrives. The server
 * authenticates the connection with the same JWT as the REST API.
 *
 * Note this is polling on the server side (yfinance has no streaming feed),
 * so updates arrive on an interval rather than per tick.
 */

let socket = null;
const listeners = new Map(); // ticker -> Set<callback>

function ensureSocket() {
  if (socket) return socket;

  const token = getToken();
  if (!token) return null; // not logged in; nothing to connect with

  socket = io(API_URL, {
    auth: { token },
    transports: ["websocket", "polling"],
    reconnectionAttempts: 5,
    reconnectionDelay: 2000,
  });

  socket.on("quote", (payload) => {
    const callbacks = listeners.get(payload.ticker);
    if (callbacks) callbacks.forEach((cb) => cb(payload));
  });

  socket.on("connect", () => {
    // Re-subscribe after a reconnect, otherwise the server has no record of
    // what this client is watching.
    const tickers = Array.from(listeners.keys());
    if (tickers.length) socket.emit("subscribe", { tickers });
  });

  return socket;
}

/**
 * Watch a ticker. Returns an unsubscribe function.
 */
export function subscribeQuote(ticker, callback) {
  if (!ticker) return () => {};
  const symbol = ticker.toUpperCase();

  const s = ensureSocket();
  if (!s) return () => {};

  if (!listeners.has(symbol)) listeners.set(symbol, new Set());
  listeners.get(symbol).add(callback);

  if (s.connected) s.emit("subscribe", { tickers: [symbol] });

  return () => {
    const callbacks = listeners.get(symbol);
    if (!callbacks) return;
    callbacks.delete(callback);
    if (callbacks.size === 0) {
      listeners.delete(symbol);
      if (s.connected) s.emit("unsubscribe", { tickers: [symbol] });
    }
  };
}

/** Drop the connection, e.g. on logout. */
export function disconnectRealtime() {
  if (socket) {
    socket.disconnect();
    socket = null;
    listeners.clear();
  }
}

export function isRealtimeConnected() {
  return Boolean(socket && socket.connected);
}
