// Интерфейс для ролика в духе Apple: iPhone, светлый Telegram, собственные иконки вместо эмодзи.
// Реплики и кнопки — по настоящему боту (booking_bot/texts.py, keyboards.py), без эмодзи.
import React from "react";
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { Icon, IconName, Logo } from "./icons";

export const inter = loadInter("normal", {
  weights: ["400", "500", "600", "700"],
  subsets: ["latin", "cyrillic"],
}).fontFamily;

export const C = {
  page: "#f5f5f7",
  ink: "#1d1d1f",
  gray: "#6e6e73",
  light: "#86868b",
  blue: "#0071e3",
  tgBlue: "#007aff",
  wallpaper: "#e8edf2",
  bubbleIn: "#ffffff",
  bubbleOut: "#007aff",
};

// ---------- анимации ----------

export const useEnter = (at: number, damping = 200, durationInFrames?: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - at, fps, config: { damping, mass: 0.9 }, durationInFrames });
};

// Плавное появление снизу с расфокусом — как в презентациях Apple.
export const Reveal: React.FC<{ at?: number; children: React.ReactNode; style?: React.CSSProperties; y?: number }> = ({
  at = 0,
  children,
  style,
  y = 30,
}) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame - at, [0, 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.25, 0.1, 0.25, 1),
  });
  return (
    <div
      style={{
        opacity: p,
        transform: `translateY(${(1 - p) * y}px)`,
        filter: `blur(${(1 - p) * 10}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

// ---------- модель чата ----------

export type Keyboard = string[][];
export type BotState = { at: number; text: string; kb?: Keyboard };
export type Item =
  | { kind: "user"; at: number; text: string }
  | { kind: "bot"; states: BotState[] }
  | { kind: "banner"; at: number; until: number; title: string; text: string };
export type Tap = { at: number; label: string };

const firstAt = (item: Item) => (item.kind === "bot" ? item.states[0].at : item.at);

// Разметка текста: **жирный**; строка «@clock …» — с иконкой слева.
const Rich: React.FC<{ text: string; color: string }> = ({ text, color }) => (
  <>
    {text.split("\n").map((line, i) => {
      const m = line.match(/^@(\w+) (.*)$/);
      const content = m ? m[2] : line;
      const parts = content.split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
        p.startsWith("**") ? (
          <b key={j} style={{ fontWeight: 600 }}>
            {p.slice(2, -2)}
          </b>
        ) : (
          <React.Fragment key={j}>{p}</React.Fragment>
        ),
      );
      return (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, minHeight: line ? undefined : 10 }}>
          {m ? <Icon name={m[1] as IconName} size={19} color={color} stroke={1.9} /> : null}
          <span>{parts}</span>
        </div>
      );
    })}
  </>
);

const Bubble: React.FC<{ side: "bot" | "user"; children: React.ReactNode }> = ({ side, children }) => (
  <div
    style={{
      alignSelf: side === "user" ? "flex-end" : "flex-start",
      maxWidth: "84%",
      background: side === "user" ? C.bubbleOut : C.bubbleIn,
      color: side === "user" ? "#fff" : "#000",
      padding: "11px 15px",
      borderRadius: 20,
      borderBottomLeftRadius: side === "bot" ? 6 : 20,
      borderBottomRightRadius: side === "user" ? 6 : 20,
      fontSize: 20,
      lineHeight: 1.38,
      boxShadow: side === "bot" ? "0 1px 1.5px rgba(0,0,0,.08)" : undefined,
    }}
  >
    {children}
  </div>
);

const KbButton: React.FC<{ label: string; taps: Tap[] }> = ({ label, taps }) => {
  const frame = useCurrentFrame();
  const tap = taps.find((t) => t.label === label && frame >= t.at - 8 && frame <= t.at + 16);
  const p = tap ? interpolate(frame, [tap.at - 8, tap.at, tap.at + 16], [0, 1, 0]) : 0;
  return (
    <div
      style={{
        flex: 1,
        background: `rgba(${Math.round(255 - 40 * p)},${Math.round(255 - 25 * p)},255,.82)`,
        color: C.tgBlue,
        borderRadius: 12,
        padding: "10px 6px",
        fontSize: 18,
        fontWeight: 500,
        textAlign: "center",
        transform: `scale(${1 - 0.04 * p})`,
        boxShadow: "0 1px 1.5px rgba(0,0,0,.06)",
      }}
    >
      {label}
    </div>
  );
};

const KeyboardView: React.FC<{ kb: Keyboard; taps: Tap[] }> = ({ kb, taps }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 5, width: "84%" }}>
    {kb.map((row, i) => (
      <div key={i} style={{ display: "flex", gap: 5 }}>
        {row.map((label) => (
          <KbButton key={label} label={label} taps={taps} />
        ))}
      </div>
    ))}
  </div>
);

// Сообщение бота, которое бот редактирует на месте (как в настоящем Telegram).
const BotMessage: React.FC<{ states: BotState[]; taps: Tap[] }> = ({ states, taps }) => {
  const frame = useCurrentFrame();
  const current = [...states].reverse().find((s) => frame >= s.at) ?? states[0];
  const first = states.indexOf(current) === 0;
  const p = interpolate(frame - current.at, [0, 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", opacity: first ? 1 : 0.4 + 0.6 * p }}>
      <Bubble side="bot">
        <Rich text={current.text} color={C.light} />
      </Bubble>
      {current.kb ? <KeyboardView kb={current.kb} taps={taps} /> : null}
    </div>
  );
};

const Appear: React.FC<{ at: number; children: React.ReactNode }> = ({ at, children }) => {
  const p = useEnter(at, 26);
  return (
    <div
      style={{
        maxHeight: interpolate(p, [0, 1], [0, 900]),
        opacity: Math.min(1, p * 1.4),
        transform: `translateY(${interpolate(p, [0, 1], [18, 0])}px) scale(${interpolate(p, [0, 1], [0.97, 1])})`,
        transformOrigin: "bottom left",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
      }}
    >
      {children}
    </div>
  );
};

// Уведомление iOS сверху экрана.
const Banner: React.FC<{ at: number; until: number; title: string; text: string }> = ({ at, until, title, text }) => {
  const frame = useCurrentFrame();
  const inP = useEnter(at, 20);
  const outP = useEnter(until, 200);
  if (frame < at) return null;
  const y = interpolate(inP - outP, [0, 1], [-170, 0]);
  return (
    <div
      style={{
        position: "absolute",
        top: 62 + y,
        left: 12,
        right: 12,
        zIndex: 5,
        background: "rgba(255,255,255,.86)",
        backdropFilter: "blur(20px)",
        borderRadius: 26,
        padding: "13px 16px",
        boxShadow: "0 10px 40px rgba(0,0,0,.16)",
        display: "flex",
        gap: 12,
        alignItems: "center",
      }}
    >
      <Logo size={42} />
      <div style={{ fontSize: 17, lineHeight: 1.3, color: "#000", flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <b style={{ fontWeight: 600 }}>{title}</b>
          <span style={{ color: C.light, fontSize: 15 }}>сейчас</span>
        </div>
        <div style={{ color: "#3c3c43" }}>{text}</div>
      </div>
    </div>
  );
};

// ---------- iPhone ----------

const StatusBar: React.FC = () => (
  <div
    style={{
      position: "absolute",
      top: 0,
      left: 0,
      right: 0,
      height: 54,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "6px 34px 0 40px",
      fontSize: 17,
      fontWeight: 600,
      color: "#000",
      zIndex: 3,
    }}
  >
    <span>9:41</span>
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <svg width="18" height="12" viewBox="0 0 18 12">
        {[0, 1, 2, 3].map((i) => (
          <rect key={i} x={i * 4.6} y={9 - i * 3} width="3.2" height={3 + i * 3} rx="1" fill="#000" />
        ))}
      </svg>
      <svg width="27" height="13" viewBox="0 0 27 13">
        <rect x="0.5" y="0.5" width="23" height="12" rx="3.5" fill="none" stroke="#000" opacity=".4" />
        <rect x="2" y="2" width="18" height="9" rx="2" fill="#000" />
        <rect x="24.5" y="4.5" width="1.6" height="4" rx=".8" fill="#000" opacity=".4" />
      </svg>
    </div>
  </div>
);

export const Phone: React.FC<{
  items: Item[];
  taps?: Tap[];
  title?: string;
  subtitle?: string;
}> = ({ items, taps = [], title = "Салон «Ножницы»", subtitle = "бот" }) => {
  const frame = useCurrentFrame();
  const visible = items.filter((it) => it.kind !== "banner" && frame >= firstAt(it) - 1);
  const banners = items.filter((it) => it.kind === "banner") as Extract<Item, { kind: "banner" }>[];
  return (
    <div
      style={{
        width: 450,
        height: 930,
        borderRadius: 74,
        padding: 5,
        background: "linear-gradient(140deg,#f4f4f6 0%,#b8babf 28%,#e9e9ec 52%,#9fa1a6 78%,#dcdde0 100%)",
        boxShadow: "0 50px 100px rgba(0,0,0,.18), 0 18px 36px rgba(0,0,0,.10)",
        fontFamily: inter,
      }}
    >
      <div style={{ width: "100%", height: "100%", borderRadius: 69, background: "#000", padding: 9 }}>
        <div
          style={{
            position: "relative",
            width: "100%",
            height: "100%",
            borderRadius: 60,
            overflow: "hidden",
            background: `linear-gradient(180deg, #dfe7ef 0%, ${C.wallpaper} 100%)`,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* Dynamic Island */}
          <div
            style={{
              position: "absolute",
              top: 12,
              left: "50%",
              width: 122,
              height: 36,
              marginLeft: -61,
              borderRadius: 20,
              background: "#000",
              zIndex: 6,
            }}
          />
          <StatusBar />
          {banners.map((b, i) => (
            <Banner key={i} {...b} />
          ))}
          {/* шапка чата */}
          <div
            style={{
              background: "rgba(249,249,249,.94)",
              borderBottom: "1px solid rgba(0,0,0,.08)",
              padding: "58px 16px 10px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              color: "#000",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", color: C.tgBlue, fontSize: 18, width: 90 }}>
              <Icon name="chevron" size={24} color={C.tgBlue} stroke={2.4} />
              Чаты
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{title}</div>
              <div style={{ fontSize: 14, color: C.light }}>{subtitle}</div>
            </div>
            <div style={{ width: 90, display: "flex", justifyContent: "flex-end" }}>
              <Logo size={40} />
            </div>
          </div>
          {/* лента: новые снизу */}
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              justifyContent: "flex-end",
              gap: 8,
              padding: "10px 12px 14px",
              overflow: "hidden",
            }}
          >
            {visible.map((it, i) => (
              <Appear key={i} at={firstAt(it)}>
                {it.kind === "user" ? (
                  <Bubble side="user">{it.text}</Bubble>
                ) : it.kind === "bot" ? (
                  <BotMessage states={it.states} taps={taps} />
                ) : null}
              </Appear>
            ))}
          </div>
          {/* поле ввода */}
          <div
            style={{
              background: "rgba(249,249,249,.94)",
              borderTop: "1px solid rgba(0,0,0,.08)",
              padding: "10px 14px 34px",
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <Icon name="attach" size={26} color={C.light} />
            <div
              style={{
                flex: 1,
                border: "1px solid rgba(0,0,0,.12)",
                borderRadius: 20,
                padding: "7px 14px",
                fontSize: 17,
                color: "#b0b0b5",
                background: "#fff",
              }}
            >
              Сообщение
            </div>
            <Icon name="mic" size={26} color={C.light} />
          </div>
        </div>
      </div>
    </div>
  );
};

// ---------- фон ----------

export const Backdrop: React.FC<{ tint?: string }> = ({ tint = "rgba(0,113,227,.10)" }) => {
  const frame = useCurrentFrame();
  const x = 70 + Math.sin(frame / 90) * 6;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: `radial-gradient(60% 70% at ${x}% 45%, ${tint} 0%, rgba(245,245,247,0) 70%), radial-gradient(80% 80% at 20% 0%, #ffffff 0%, ${C.page} 60%)`,
      }}
    />
  );
};
