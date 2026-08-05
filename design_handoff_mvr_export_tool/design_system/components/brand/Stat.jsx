import React from "react";

/** Big numeric proof-point ("30+ Jahre", "50 Mitarbeiter"). */
export function Stat({ value, label, onDark = false, align = "left", style }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px", textAlign: align, alignItems: align === "center" ? "center" : "flex-start", ...style }}>
      <span style={{ fontFamily: "var(--font-display)", fontSize: "clamp(44px, 6vw, 72px)", fontWeight: "var(--fw-bold)", lineHeight: 1, letterSpacing: "var(--tracking-display)", color: onDark ? "var(--brand-accent)" : "var(--brand-primary)" }}>{value}</span>
      <span style={{ fontFamily: "var(--font-heading)", fontSize: "13px", fontWeight: "var(--fw-semibold)", letterSpacing: "var(--tracking-label)", textTransform: "uppercase", color: onDark ? "var(--text-inverse-muted)" : "var(--text-muted)" }}>{label}</span>
    </div>
  );
}
