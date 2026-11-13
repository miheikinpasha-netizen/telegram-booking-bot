// Промо-ролик целиком и обложка для Kwork.
import React from "react";
import { AbsoluteFill } from "remotion";
import { TransitionSeries, springTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { Icon } from "./icons";
import { Backdrop, C, inter, Item, Phone } from "./tg";
import {
  AdminScene, BookingScene, FeaturesScene, IntroScene, OutroScene, PricesScene, RescheduleScene,
} from "./scenes";

export const SCENES = {
  intro: 120,
  booking: 470,
  admin: 200,
  reschedule: 220,
  prices: 260,
  features: 170,
  outro: 160,
};
export const TRANSITION = 24;
export const PROMO_DURATION =
  Object.values(SCENES).reduce((a, b) => a + b, 0) - TRANSITION * (Object.keys(SCENES).length - 1);

const t = () => springTiming({ config: { damping: 200 }, durationInFrames: TRANSITION });

export const Promo: React.FC = () => (
  <TransitionSeries>
    <TransitionSeries.Sequence name="Интро" durationInFrames={SCENES.intro}>
      <IntroScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={t()} />
    <TransitionSeries.Sequence name="Запись" durationInFrames={SCENES.booking}>
      <BookingScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({ direction: "from-right" })} timing={t()} />
    <TransitionSeries.Sequence name="Администратор" durationInFrames={SCENES.admin}>
      <AdminScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({ direction: "from-right" })} timing={t()} />
    <TransitionSeries.Sequence name="Перенос" durationInFrames={SCENES.reschedule}>
      <RescheduleScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({ direction: "from-right" })} timing={t()} />
    <TransitionSeries.Sequence name="Цены" durationInFrames={SCENES.prices}>
      <PricesScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={t()} />
    <TransitionSeries.Sequence name="Возможности" durationInFrames={SCENES.features}>
      <FeaturesScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={t()} />
    <TransitionSeries.Sequence name="Финал" durationInFrames={SCENES.outro}>
      <OutroScene />
    </TransitionSeries.Sequence>
  </TransitionSeries>
);

// ---------- обложка для Kwork ----------

const COVER_ITEMS: Item[] = [
  { kind: "user", at: -100, text: "Записаться" },
  {
    kind: "bot",
    states: [
      {
        at: -100,
        text: "**Женская стрижка**, вт, 17 ноября\n@person Мастер: Анна\nВыберите время:",
        kb: [
          ["10:00", "10:30", "11:00", "11:30"],
          ["12:00", "12:30", "13:00", "13:30"],
          ["14:00", "14:30", "15:00", "15:30"],
        ],
      },
    ],
  },
  {
    kind: "bot",
    states: [
      {
        at: -100,
        text: "**Вы записаны**\n\n**Женская стрижка**\n@clock вт, 17 ноября, 11:00\n@person Мастер: Анна\n@ruble 1 800 ₽",
      },
    ],
  },
];

export const Cover: React.FC<{ title: string; points: string[] }> = ({ title, points }) => (
  <AbsoluteFill style={{ fontFamily: inter }}>
    <Backdrop />
    <div style={{ position: "absolute", left: 84, top: 120, width: 660 }}>
      <div style={{ fontSize: 26, fontWeight: 600, color: C.blue }}>Python · aiogram 3</div>
      <div
        style={{
          fontSize: 72,
          fontWeight: 700,
          color: C.ink,
          lineHeight: 1.04,
          letterSpacing: "-0.035em",
          marginTop: 14,
        }}
      >
        {title}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 20, marginTop: 46 }}>
        {points.map((p) => (
          <div key={p} style={{ fontSize: 32, color: C.ink, display: "flex", gap: 16, alignItems: "center" }}>
            <Icon name="check" size={30} color={C.blue} stroke={2.2} />
            {p}
          </div>
        ))}
      </div>
    </div>
    <div style={{ position: "absolute", right: 70, top: 46, transform: "scale(0.84)", transformOrigin: "top right" }}>
      <Phone items={COVER_ITEMS} />
    </div>
  </AbsoluteFill>
);
