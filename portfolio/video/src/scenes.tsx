// Сцены промо-ролика в духе презентаций Apple. Реплики и кнопки — по настоящему боту.
import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Icon, IconName, Logo } from "./icons";
import { Backdrop, C, inter, Item, Phone, Reveal, Tap } from "./tg";

// ---------- данные чата ----------

const SERVICES_KB = [
  ["Женская стрижка · 1 800 ₽"],
  ["Мужская стрижка · 1 000 ₽"],
  ["Окрашивание · 4 500 ₽"],
  ["Укладка · 1 200 ₽"],
];
const DAYS = [
  ["пн, 16 ноября", "вт, 17 ноября"],
  ["ср, 18 ноября", "чт, 19 ноября"],
  ["пт, 20 ноября"],
];
const ANNA_TIMES = [
  ["10:00", "10:30", "11:00", "11:30"],
  ["12:00", "12:30", "13:00", "13:30"],
  ["14:00", "14:30", "15:00", "15:30"],
  ["16:00", "16:30", "17:00", "17:30"],
  ["18:00"],
];
const CARD = "**Женская стрижка**\n@clock вт, 17 ноября, 11:00\n@person Мастер: Анна";

// ---------- общие элементы ----------

const Headline: React.FC<{ children: React.ReactNode; size?: number }> = ({ children, size = 88 }) => (
  <div style={{ fontSize: size, fontWeight: 700, color: C.ink, lineHeight: 1.04, letterSpacing: "-0.035em" }}>
    {children}
  </div>
);

const Eyebrow: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ fontSize: 28, fontWeight: 600, color: C.blue, letterSpacing: "-0.01em" }}>{children}</div>
);

const Point: React.FC<{ at: number; icon: IconName; text: string }> = ({ at, icon, text }) => (
  <Reveal at={at} y={20} style={{ display: "flex", gap: 20, alignItems: "center" }}>
    <div
      style={{
        width: 56,
        height: 56,
        borderRadius: 16,
        background: "#fff",
        boxShadow: "0 1px 3px rgba(0,0,0,.08)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <Icon name={icon} size={28} color={C.blue} />
    </div>
    <div style={{ fontSize: 32, color: C.ink, letterSpacing: "-0.01em" }}>{text}</div>
  </Reveal>
);

// Телефон справа: мягко въезжает и чуть «дышит».
const PhoneSlot: React.FC<{ items: Item[]; taps: Tap[]; subtitle?: string }> = ({ items, taps, subtitle }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  return (
    <div
      style={{
        position: "absolute",
        right: 230,
        top: 75,
        opacity: p,
        transform: `translateY(${(1 - p) * 90 + Math.sin(frame / 50) * 4}px) scale(${0.94 + 0.06 * p})`,
      }}
    >
      <Phone items={items} taps={taps} subtitle={subtitle} />
    </div>
  );
};

const Layout: React.FC<{
  eyebrow: string;
  title: React.ReactNode;
  children?: React.ReactNode;
  items: Item[];
  taps: Tap[];
  subtitle?: string;
  tint?: string;
}> = ({ eyebrow, title, children, items, taps, subtitle, tint }) => (
  <AbsoluteFill style={{ fontFamily: inter }}>
    <Backdrop tint={tint} />
    <div style={{ position: "absolute", left: 160, top: 190, width: 820 }}>
      <Reveal at={2}>
        <Eyebrow>{eyebrow}</Eyebrow>
      </Reveal>
      <Reveal at={6} style={{ marginTop: 18 }}>
        <Headline>{title}</Headline>
      </Reveal>
      <div style={{ display: "flex", flexDirection: "column", gap: 24, marginTop: 56 }}>{children}</div>
    </div>
    <PhoneSlot items={items} taps={taps} subtitle={subtitle} />
  </AbsoluteFill>
);

// ---------- 1. Интро ----------

export const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const logo = interpolate(frame, [0, 26], [0, 1], { extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1) });
  return (
    <AbsoluteFill style={{ fontFamily: inter, alignItems: "center", justifyContent: "center", textAlign: "center" }}>
      <Backdrop tint="rgba(120,90,255,.08)" />
      <div style={{ opacity: logo, transform: `scale(${0.8 + 0.2 * logo})` }}>
        <Logo size={128} />
      </div>
      <Reveal at={12} style={{ marginTop: 52 }}>
        <Headline size={120}>Онлайн-запись.</Headline>
      </Reveal>
      <Reveal at={20}>
        <div
          style={{
            fontSize: 120,
            fontWeight: 700,
            letterSpacing: "-0.035em",
            lineHeight: 1.08,
            background: "linear-gradient(90deg,#0071e3,#7a5cff 60%,#c346c2)",
            WebkitBackgroundClip: "text",
            color: "transparent",
          }}
        >
          Прямо в Telegram.
        </div>
      </Reveal>
      <Reveal at={34} style={{ marginTop: 34 }}>
        <div style={{ fontSize: 38, color: C.gray, letterSpacing: "-0.01em" }}>
          Для салонов, барбершопов, массажа и репетиторов.
        </div>
      </Reveal>
    </AbsoluteFill>
  );
};

// ---------- 2. Запись клиента ----------

const BOOKING_ITEMS: Item[] = [
  { kind: "user", at: 12, text: "Записаться" },
  {
    kind: "bot",
    states: [
      { at: 28, text: "Выберите услугу:", kb: [...SERVICES_KB, ["Отмена"]] },
      {
        at: 80,
        text: "**Женская стрижка**, 60 мин.\nВыберите мастера:",
        kb: [["Любой свободный мастер"], ["Анна"], ["Игорь"], ["К услугам"]],
      },
      {
        at: 128,
        text: "**Женская стрижка**, 60 мин.\n@person Мастер: Анна\nВыберите дату:",
        kb: [...DAYS, ["К мастерам"]],
      },
      {
        at: 176,
        text: "**Женская стрижка**, вт, 17 ноября\n@person Мастер: Анна\nВыберите время:",
        kb: [...ANNA_TIMES, ["К датам"]],
      },
      { at: 226, text: CARD },
    ],
  },
  { kind: "bot", states: [{ at: 240, text: "Как к вам обращаться? Напишите имя." }] },
  { kind: "user", at: 268, text: "Ольга" },
  { kind: "bot", states: [{ at: 282, text: "Оставьте номер телефона: нажмите кнопку ниже или напишите номер." }] },
  { kind: "user", at: 310, text: "+7 999 123-45-67" },
  {
    kind: "bot",
    states: [
      {
        at: 330,
        text: `Проверьте запись:\n\n${CARD}\n@ruble 1 800 ₽\n@phone Ольга, +7 999 123-45-67`,
        kb: [["Подтвердить", "Отменить"]],
      },
      {
        at: 384,
        text: `**Вы записаны**\n\n${CARD}\n@ruble 1 800 ₽\n\nНапомним за 2 часа до визита. Перенести или отменить запись можно в разделе «Мои записи».`,
      },
    ],
  },
];
const BOOKING_TAPS: Tap[] = [
  { at: 66, label: "Женская стрижка · 1 800 ₽" },
  { at: 114, label: "Анна" },
  { at: 162, label: "вт, 17 ноября" },
  { at: 212, label: "11:00" },
  { at: 370, label: "Подтвердить" },
];
const STEPS: [number, string][] = [
  [0, "Услуга"],
  [80, "Мастер"],
  [128, "День и время"],
  [240, "Имя и телефон"],
  [384, "Готово"],
];

export const BookingScene: React.FC = () => {
  const frame = useCurrentFrame();
  const active = STEPS.filter(([at]) => frame >= at).length - 1;
  return (
    <Layout eyebrow="Для клиента" title={<>Запись в пару<br />касаний.</>} items={BOOKING_ITEMS} taps={BOOKING_TAPS}>
      {STEPS.map(([, label], i) => {
        const on = i === active;
        const done = i < active;
        return (
          <Reveal key={label} at={14 + i * 4} y={16}>
            <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 24,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 22,
                  fontWeight: 600,
                  color: on ? "#fff" : done ? C.blue : C.light,
                  background: on ? C.ink : "transparent",
                  border: on ? "none" : `1.5px solid ${done ? C.blue : "#d2d2d7"}`,
                }}
              >
                {done ? <Icon name="check" size={24} color={C.blue} stroke={2.4} /> : i + 1}
              </div>
              <span
                style={{
                  fontSize: 36,
                  letterSpacing: "-0.015em",
                  color: on ? C.ink : done ? C.gray : C.light,
                  fontWeight: on ? 600 : 400,
                }}
              >
                {label}
              </span>
            </div>
          </Reveal>
        );
      })}
    </Layout>
  );
};

// ---------- 3. Уведомление администратору ----------

const ADMIN_ITEMS: Item[] = [
  { kind: "banner", at: 14, until: 66, title: "Салон «Ножницы»", text: "Новая запись · Женская стрижка, вт 11:00" },
  {
    kind: "bot",
    states: [
      {
        at: 60,
        text: `**Новая запись**\n\n${CARD}\n@ruble 1 800 ₽\n@phone Ольга, +7 999 123-45-67\n№ 12`,
        kb: [["Отменить запись"]],
      },
    ],
  },
  { kind: "user", at: 112, text: "/today" },
  { kind: "bot", states: [{ at: 126, text: "**Сегодня**: 3 записи" }] },
];

export const AdminScene: React.FC = () => (
  <Layout
    eyebrow="Для владельца"
    title={<>Каждая запись —<br />сразу у вас.</>}
    items={ADMIN_ITEMS}
    taps={[]}
    subtitle="вы — администратор"
    tint="rgba(52,199,89,.10)"
  >
    <Point at={18} icon="bell" text="Запись, перенос и отмена — в уведомлениях" />
    <Point at={24} icon="phone" text="Имя и телефон клиента в одном сообщении" />
    <Point at={30} icon="calendar" text="Расписание на день и неделю" />
    <Point at={36} icon="cross" text="Отмена одной кнопкой" />
  </Layout>
);

// ---------- 4. Перенос записи ----------

const MOVE_CARD = `${CARD}\n@ruble 1 800 ₽`;
const RESCHEDULE_ITEMS: Item[] = [
  { kind: "user", at: 10, text: "Мои записи" },
  {
    kind: "bot",
    states: [
      {
        at: 24,
        text: `Ваши записи:\n\n${MOVE_CARD}`,
        kb: [["Перенести вт, 17 ноября, 11:00"], ["Отменить вт, 17 ноября, 11:00"]],
      },
      { at: 74, text: `Перенос записи:\n\n${MOVE_CARD}\n\nВыберите новую дату:`, kb: [...DAYS, ["Не переносить"]] },
      { at: 118, text: "Перенос: **Женская стрижка**, чт, 19 ноября\nВыберите время:", kb: [...ANNA_TIMES, ["К датам"]] },
      {
        at: 166,
        text: "**Запись перенесена**\n\n**Женская стрижка**\n@clock чт, 19 ноября, 15:00\n@person Мастер: Анна\n@ruble 1 800 ₽",
      },
    ],
  },
];
const RESCHEDULE_TAPS: Tap[] = [
  { at: 60, label: "Перенести вт, 17 ноября, 11:00" },
  { at: 104, label: "чт, 19 ноября" },
  { at: 152, label: "15:00" },
];

export const RescheduleScene: React.FC = () => (
  <Layout
    eyebrow="Без звонков"
    title={<>Клиент сам<br />переносит запись.</>}
    items={RESCHEDULE_ITEMS}
    taps={RESCHEDULE_TAPS}
    tint="rgba(255,149,0,.10)"
  >
    <Point at={18} icon="repeat" text="Только свободное время мастера" />
    <Point at={24} icon="bell" text="Напоминание придёт заново" />
    <Point at={30} icon="lock" text="Чужую запись изменить нельзя" />
  </Layout>
);

// ---------- 5. Цены из Telegram ----------

const SERVICE_CARD = (price: string) =>
  `**Женская стрижка**\n@ruble Цена: ${price}\n@hourglass Длительность: 60 мин\n@eye Видна клиентам`;
const PRICES_ITEMS: Item[] = [
  { kind: "user", at: 10, text: "/admin" },
  {
    kind: "bot",
    states: [
      {
        at: 24,
        text: "**Панель администратора**\n\n@calendar Расписание на день и неделю\n@sliders Услуги и цены\n@bell Уведомления о записях",
        kb: [["Сегодня", "Завтра", "Неделя"], ["Услуги и цены"]],
      },
      { at: 70, text: "**Услуги и цены**\nВыберите услугу:", kb: SERVICES_KB },
      {
        at: 114,
        text: SERVICE_CARD("1 800 ₽"),
        kb: [["Изменить цену"], ["Изменить длительность"], ["Скрыть от клиентов"], ["Все услуги"]],
      },
    ],
  },
  { kind: "bot", states: [{ at: 158, text: "«Женская стрижка»: напишите новую цену в рублях, например 2000." }] },
  { kind: "user", at: 186, text: "2000" },
  { kind: "bot", states: [{ at: 200, text: `**Сохранено**\n\n${SERVICE_CARD("2 000 ₽")}` }] },
];
const PRICES_TAPS: Tap[] = [
  { at: 56, label: "Услуги и цены" },
  { at: 100, label: "Женская стрижка · 1 800 ₽" },
  { at: 144, label: "Изменить цену" },
];

export const PricesScene: React.FC = () => (
  <Layout
    eyebrow="Без программиста"
    title={<>Цены меняются<br />прямо в Telegram.</>}
    items={PRICES_ITEMS}
    taps={PRICES_TAPS}
    subtitle="вы — администратор"
    tint="rgba(175,82,222,.10)"
  >
    <Point at={18} icon="sliders" text="Цена и длительность — в два касания" />
    <Point at={24} icon="eye" text="Скрыть услугу на время и вернуть" />
    <Point at={30} icon="bolt" text="Клиенты сразу видят изменения" />
  </Layout>
);

// ---------- 6. Возможности ----------

const FEATURES: [IconName, string, string][] = [
  ["people", "Мастера и графики", "У каждого свои дни и часы. Или «любой свободный»."],
  ["lock", "Без двойных записей", "Время проверяется в одной транзакции базы."],
  ["bell", "Напоминания", "Клиенту — за 2 часа до визита, автоматически."],
  ["question", "Частые вопросы", "Адрес, график, оплата, подготовка."],
  ["eye", "Демо для владельца", "Сторона администратора — в один клик."],
  ["shield", "30 автотестов", "Запись, перенос, права доступа и цены."],
];

export const FeaturesScene: React.FC = () => (
  <AbsoluteFill style={{ fontFamily: inter, padding: "120px 160px" }}>
    <Backdrop tint="rgba(0,113,227,.06)" />
    <Reveal at={2}>
      <Headline>И всё это — уже внутри.</Headline>
    </Reveal>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 28, marginTop: 64 }}>
      {FEATURES.map(([icon, title, text], i) => (
        <Reveal key={title} at={10 + i * 5} y={24}>
          <div
            style={{
              height: 290,
              borderRadius: 30,
              padding: "40px 38px",
              background: "#fff",
              boxShadow: "0 2px 6px rgba(0,0,0,.04), 0 12px 32px rgba(0,0,0,.05)",
              boxSizing: "border-box",
            }}
          >
            <Icon name={icon} size={46} color={C.blue} stroke={1.6} />
            <div style={{ fontSize: 36, fontWeight: 600, color: C.ink, marginTop: 26, letterSpacing: "-0.02em" }}>
              {title}
            </div>
            <div style={{ fontSize: 26, color: C.gray, marginTop: 12, lineHeight: 1.38 }}>{text}</div>
          </div>
        </Reveal>
      ))}
    </div>
  </AbsoluteFill>
);

// ---------- 7. Финал ----------

export const OutroScene: React.FC = () => (
  <AbsoluteFill style={{ fontFamily: inter, alignItems: "center", justifyContent: "center", textAlign: "center" }}>
    <Backdrop tint="rgba(120,90,255,.08)" />
    <Reveal at={2}>
      <Logo size={110} />
    </Reveal>
    <Reveal at={8} style={{ marginTop: 44 }}>
      <Headline size={104}>Попробуйте сами.</Headline>
    </Reveal>
    <Reveal at={18} style={{ marginTop: 40 }}>
      <div
        style={{
          padding: "22px 46px",
          borderRadius: 50,
          background: C.blue,
          color: "#fff",
          fontSize: 40,
          fontWeight: 600,
          letterSpacing: "-0.01em",
        }}
      >
        @nozhnitsy_demo_booking_bot
      </div>
    </Reveal>
    <Reveal at={28} style={{ marginTop: 48 }}>
      <div style={{ fontSize: 36, color: C.ink, letterSpacing: "-0.01em" }}>
        Настрою под ваш бизнес: услуги, мастера, график, тексты.
      </div>
    </Reveal>
    <Reveal at={34} style={{ marginTop: 14 }}>
      <div style={{ fontSize: 28, color: C.light }}>Python · aiogram 3 · SQLite · исходный код передаётся вам</div>
    </Reveal>
  </AbsoluteFill>
);
