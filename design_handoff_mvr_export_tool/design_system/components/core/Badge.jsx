import React from "react";

const tones = {
  neutral: { background: "var(--gray-100)", color: "var(--gray-700)" },
  brand:   { background: "var(--blue-50)", color: "var(--blue-700)" },
  solid:   { background: "var(--brand-primary)", color: "var(--white)" },
  success: { background: "#e4f4ec", color: "var(--green-500)" },
  warning: { background: "#fbf0da", color: "#a9740f" },
  danger:  { background: "#fbe4e4", color: "var(--red-500)" },
  onDark:  { background: "rgba(255,255,255,0.14)", color: "var(--white)" },
};

/** Small status/label pill. */
export function Badge({ tone = "neutral", children, style, ...rest }) {
  const s = {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    fontFamily: "var(--font-heading)",
    fontSize: "12px",
    fontWeight: "var(--fw-semibold)",
    letterSpacing: "var(--tracking-label)",
    textTransform: "uppercase",
    padding: "4px 10px",
    borderRadius: "var(--radius-sm)",
    lineHeight: 1,
    ...tones[tone],
    ...style,
  };
  return <span style={s} {...rest}>{children}</span>;
}
