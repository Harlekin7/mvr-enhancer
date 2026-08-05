import React from "react";

const pads = { none: "0", sm: "16px", md: "24px", lg: "32px" };

const tones = {
  light: { background: "var(--surface-card)", color: "var(--text-body)", border: "1px solid var(--border-subtle)" },
  sunken: { background: "var(--surface-sunken)", color: "var(--text-body)", border: "1px solid var(--border-subtle)" },
  dark: { background: "var(--surface-card-dark)", color: "var(--text-inverse)", border: "1px solid var(--border-dark)" },
};

/** Base surface container. */
export function Card({ tone = "light", padding = "md", elevation = "sm", hoverable = false, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const shadowMap = { none: "none", xs: "var(--shadow-xs)", sm: "var(--shadow-sm)", md: "var(--shadow-md)", lg: "var(--shadow-lg)" };
  const s = {
    borderRadius: "var(--radius-lg)",
    padding: pads[padding],
    boxShadow: hoverable && hover ? "var(--shadow-lg)" : shadowMap[elevation],
    transform: hoverable && hover ? "translateY(-4px)" : "none",
    transition: "box-shadow var(--dur-base) var(--ease-standard), transform var(--dur-base) var(--ease-standard)",
    ...tones[tone],
    ...style,
  };
  const handlers = hoverable ? { onMouseEnter: () => setHover(true), onMouseLeave: () => setHover(false) } : {};
  return <div style={s} {...handlers} {...rest}>{children}</div>;
}
