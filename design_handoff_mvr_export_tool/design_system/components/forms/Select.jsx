import React from "react";

/** Labeled native select. */
export function Select({ label, hint, options = [], onDark = false, id, style, ...rest }) {
  const selId = id || (label ? "sel-" + label.replace(/\s+/g, "-").toLowerCase() : undefined);
  const field = {
    width: "100%",
    appearance: "none",
    fontFamily: "var(--font-body)",
    fontSize: "15px",
    color: onDark ? "var(--white)" : "var(--text-heading)",
    background: (onDark ? "rgba(255,255,255,0.06)" : "var(--white)") +
      " url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23566575' stroke-width='2.5'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\") no-repeat right 14px center",
    border: "1px solid " + (onDark ? "rgba(255,255,255,0.22)" : "var(--border-default)"),
    borderRadius: "var(--radius-sm)",
    padding: "11px 40px 11px 14px",
    outline: "none",
    boxSizing: "border-box",
    cursor: "pointer",
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px", ...style }}>
      {label && (
        <label htmlFor={selId} style={{ fontFamily: "var(--font-heading)", fontSize: "12px", fontWeight: "var(--fw-semibold)", letterSpacing: "var(--tracking-label)", textTransform: "uppercase", color: onDark ? "var(--text-inverse)" : "var(--text-heading)" }}>{label}</label>
      )}
      <select id={selId} style={field} {...rest}>
        {options.map((o) => {
          const val = typeof o === "string" ? o : o.value;
          const lbl = typeof o === "string" ? o : o.label;
          return <option key={val} value={val}>{lbl}</option>;
        })}
      </select>
      {hint && <span style={{ fontSize: "13px", color: onDark ? "var(--text-inverse-muted)" : "var(--text-muted)" }}>{hint}</span>}
    </div>
  );
}
