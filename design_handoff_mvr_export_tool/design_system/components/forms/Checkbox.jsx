import React from "react";

/** Checkbox with label. */
export function Checkbox({ label, checked, onChange, disabled = false, onDark = false, style, ...rest }) {
  const box = {
    width: "20px",
    height: "20px",
    flexShrink: 0,
    borderRadius: "var(--radius-sm)",
    border: "2px solid " + (checked ? "var(--brand-primary)" : onDark ? "rgba(255,255,255,0.4)" : "var(--border-strong)"),
    background: checked ? "var(--brand-primary)" : "transparent",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "all var(--dur-fast) var(--ease-standard)",
  };
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: "10px", cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1, ...style }}>
      <input type="checkbox" checked={checked} onChange={onChange} disabled={disabled} style={{ position: "absolute", opacity: 0, width: 0, height: 0 }} {...rest} />
      <span style={box}>
        {checked && (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
        )}
      </span>
      {label && <span style={{ fontFamily: "var(--font-body)", fontSize: "15px", color: onDark ? "var(--text-inverse)" : "var(--text-body)" }}>{label}</span>}
    </label>
  );
}
