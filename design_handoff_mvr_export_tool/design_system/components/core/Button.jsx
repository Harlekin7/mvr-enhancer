import React from "react";

const sizes = {
  sm: { fontSize: "13px", padding: "8px 16px", height: "36px" },
  md: { fontSize: "15px", padding: "11px 22px", height: "44px" },
  lg: { fontSize: "17px", padding: "15px 30px", height: "54px" },
};

const base = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "8px",
  fontFamily: "var(--font-heading)",
  fontWeight: "var(--fw-semibold)",
  letterSpacing: "var(--tracking-label)",
  textTransform: "uppercase",
  border: "var(--border-width-strong) solid transparent",
  borderRadius: "var(--radius-sm)",
  cursor: "pointer",
  textDecoration: "none",
  whiteSpace: "nowrap",
  transition: "background var(--dur-base) var(--ease-standard), color var(--dur-base) var(--ease-standard), border-color var(--dur-base) var(--ease-standard), transform var(--dur-fast) var(--ease-standard)",
};

const variants = {
  primary: { background: "var(--brand-primary)", color: "var(--white)", borderColor: "var(--brand-primary)" },
  secondary: { background: "transparent", color: "var(--brand-primary)", borderColor: "var(--brand-primary)" },
  ghost: { background: "transparent", color: "var(--text-body)", borderColor: "transparent", textTransform: "none", letterSpacing: "normal", fontFamily: "var(--font-body)" },
  onDark: { background: "var(--white)", color: "var(--navy-900)", borderColor: "var(--white)" },
  onDarkOutline: { background: "transparent", color: "var(--white)", borderColor: "rgba(255,255,255,0.5)" },
};

/**
 * Groh-P.A. primary action button. Uppercase, tracked, crisp corners.
 */
export function Button({
  variant = "primary",
  size = "md",
  disabled = false,
  iconLeft,
  iconRight,
  as = "button",
  children,
  style,
  ...rest
}) {
  const Tag = as;
  const s = {
    ...base,
    ...sizes[size],
    ...variants[variant],
    ...(disabled ? { opacity: 0.45, pointerEvents: "none" } : {}),
    ...style,
  };
  return (
    <Tag style={s} disabled={as === "button" ? disabled : undefined} {...rest}>
      {iconLeft}
      {children}
      {iconRight}
    </Tag>
  );
}
