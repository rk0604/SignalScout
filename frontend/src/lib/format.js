/* Shared number/label formatting so every page renders values the same way. */

export const money = (n, digits = 2) =>
  n == null
    ? "—"
    : n.toLocaleString(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });

export const usd = (n, digits = 2) => (n == null ? "—" : `$${money(n, digits)}`);

export const signed = (n, digits = 2) =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;

export const signedPct = (n, digits = 2) => (n == null ? "—" : `${signed(n, digits)}%`);

/* Direction is carried by a glyph as well as colour, so meaning survives for
   colour-blind readers and in print. */
export const arrow = (n) => (n == null || n === 0 ? "" : n > 0 ? "▲" : "▼");

export const toneClass = (n) => (n == null ? "flat" : n > 0 ? "up" : n < 0 ? "down" : "flat");

export const badgeClass = (n) =>
  n == null ? "badge-neutral" : n > 0 ? "badge-up" : n < 0 ? "badge-down" : "badge-neutral";

/* Categorical chart slots — validated against white. Assigned in fixed order
   and never cycled; the tail folds into "Other". */
export const SERIES = [
  "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
  "#e87ba4", "#008300", "#4a3aa7", "#e34948",
];
export const OTHER_COLOR = "#94A3B8";
