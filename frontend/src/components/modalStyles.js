/*
 * Shared react-modal styling.
 *
 * Previously each modal hardcoded its own colours inline, so a token change
 * had to be repeated in three files and they drifted. One definition here
 * keeps every modal on the terminal palette.
 */
export const terminalModalStyles = {
  overlay: {
    backgroundColor: "rgba(0, 0, 0, 0.82)",
    zIndex: 50,
  },
  content: {
    color: "var(--text)",
    background: "var(--panel)",
    border: "1px solid var(--border)",
    borderRadius: "3px",
    padding: "16px 18px",
    maxWidth: "84vw",
    inset: "32px",
    margin: "auto",
    textAlign: "left",
    overflowY: "auto",
  },
};

export default terminalModalStyles;
