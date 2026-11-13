import { Composition, Folder } from "remotion";
import { Cover, PROMO_DURATION, Promo, SCENES } from "./Promo";
import {
  AdminScene, BookingScene, FeaturesScene, IntroScene, OutroScene, PricesScene, RescheduleScene,
} from "./scenes";

const HD = { width: 1920, height: 1080, fps: 30 };

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Promo" component={Promo} durationInFrames={PROMO_DURATION} {...HD} />
    <Composition
      id="Cover"
      component={Cover}
      durationInFrames={1}
      width={1320}
      height={880}
      fps={30}
      defaultProps={{
        title: "Telegram-бот онлайн-записи",
        points: [
          "Клиенты записываются сами 24/7",
          "Мастера и графики без накладок",
          "Напоминания, перенос и отмена",
          "Уведомления и цены — в Telegram",
        ],
      }}
    />
    <Folder name="Scenes">
      <Composition id="Intro" component={IntroScene} durationInFrames={SCENES.intro} {...HD} />
      <Composition id="Booking" component={BookingScene} durationInFrames={SCENES.booking} {...HD} />
      <Composition id="Admin" component={AdminScene} durationInFrames={SCENES.admin} {...HD} />
      <Composition id="Reschedule" component={RescheduleScene} durationInFrames={SCENES.reschedule} {...HD} />
      <Composition id="Prices" component={PricesScene} durationInFrames={SCENES.prices} {...HD} />
      <Composition id="Features" component={FeaturesScene} durationInFrames={SCENES.features} {...HD} />
      <Composition id="Outro" component={OutroScene} durationInFrames={SCENES.outro} {...HD} />
    </Folder>
  </>
);
