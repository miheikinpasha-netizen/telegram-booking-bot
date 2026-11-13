// Собственные линейные иконки (SVG) — вместо эмодзи. Стиль: тонкая линия, скруглённые концы.
import React from "react";

export type IconName =
  | "logo" | "clock" | "calendar" | "person" | "people" | "ruble" | "phone" | "check" | "bell"
  | "repeat" | "lock" | "sliders" | "question" | "eye" | "shield" | "list" | "cross" | "chevron"
  | "attach" | "mic" | "hourglass" | "bolt";

const PATHS: Record<Exclude<IconName, "logo">, React.ReactNode> = {
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15" rx="3" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5" />
    </>
  ),
  people: (
    <>
      <circle cx="9" cy="9" r="3.2" />
      <path d="M3 19.5c.6-3.2 3-5 6-5s5.4 1.8 6 5" />
      <path d="M15.5 6.2a3 3 0 0 1 0 5.6M18 14.8c1.6.6 2.6 2.1 3 4.7" />
    </>
  ),
  ruble: <path d="M8 20V4h5.5a4 4 0 0 1 0 8H6M6 16h8.5" />,
  phone: <path d="M6.5 3.5h3l1.5 4-2 1.3a10 10 0 0 0 6.2 6.2l1.3-2 4 1.5v3a2 2 0 0 1-2 2A15.5 15.5 0 0 1 4.5 5.5a2 2 0 0 1 2-2z" />,
  check: <path d="M5 12.5l4.2 4.2L19 7" />,
  bell: (
    <>
      <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z" />
      <path d="M10 20.5a2.2 2.2 0 0 0 4 0" />
    </>
  ),
  repeat: (
    <>
      <path d="M4.5 11V9.5a3 3 0 0 1 3-3h11M15.5 3.5l3 3-3 3" />
      <path d="M19.5 13v1.5a3 3 0 0 1-3 3h-11M8.5 20.5l-3-3 3-3" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="10.5" width="14" height="10" rx="2.5" />
      <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
    </>
  ),
  sliders: (
    <>
      <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
      <circle cx="15" cy="7" r="2" />
      <circle cx="9" cy="17" r="2" />
    </>
  ),
  question: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M9.6 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.4M12 16.8v.2" />
    </>
  ),
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6z" />
      <path d="M8.5 12l2.4 2.4L15.5 9.8" />
    </>
  ),
  list: <path d="M9 7h11M9 12h11M9 17h11M4.5 7h.01M4.5 12h.01M4.5 17h.01" />,
  cross: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  chevron: <path d="M14.5 5l-7 7 7 7" />,
  attach: <path d="M19 11.5l-7.2 7.2a4.5 4.5 0 0 1-6.4-6.4l7.6-7.6a3 3 0 0 1 4.2 4.2l-7.4 7.4a1.5 1.5 0 0 1-2.1-2.1l6.8-6.8" />,
  mic: (
    <>
      <rect x="9" y="3.5" width="6" height="11" rx="3" />
      <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5" />
    </>
  ),
  hourglass: <path d="M7 3.5h10M7 20.5h10M8 3.5c0 4.5 8 5 8 8.5s-8 4-8 8.5M16 3.5c0 4.5-8 5-8 8.5s8 4 8 8.5" />,
  bolt: <path d="M13 3L5 13.5h6L10 21l8-10.5h-6z" />,
};

export const Icon: React.FC<{ name: IconName; size?: number; color?: string; stroke?: number }> = ({
  name,
  size = 24,
  color = "currentColor",
  stroke = 1.8,
}) => {
  if (name === "logo") return <Logo size={size} />;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0, display: "block" }}
    >
      {PATHS[name]}
    </svg>
  );
};

// Логотип «Ножницы»: нарисованные ножницы на тёмном круге.
export const Logo: React.FC<{ size: number }> = ({ size }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" style={{ flexShrink: 0, display: "block" }}>
    <defs>
      <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#2c2c2e" />
        <stop offset="1" stopColor="#000" />
      </linearGradient>
    </defs>
    <circle cx="32" cy="32" r="32" fill="url(#lg)" />
    <g fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round">
      <circle cx="22" cy="42" r="6.5" />
      <circle cx="42" cy="42" r="6.5" />
      <path d="M26.5 37.5L44 16M37.5 37.5L20 16" />
    </g>
    <circle cx="32" cy="29.6" r="1.8" fill="#fff" />
  </svg>
);
