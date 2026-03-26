import React from "react";
import { Composition } from "remotion";
import { OasisPromo } from "./compositions/OasisPromo";
import { QuoteDrop } from "./compositions/QuoteDrop";
import { CeoLog } from "./compositions/CeoLog";
import { SkoolIntro } from "./compositions/SkoolIntro";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="OasisPromo"
        component={OasisPromo}
        durationInFrames={300}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          headline: "AI That Actually Works",
          subheadline: "OASIS AI Solutions",
          ctaText: "Book a Free Strategy Call",
        }}
      />
      <Composition
        id="QuoteDrop"
        component={QuoteDrop}
        durationInFrames={150}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          quote: "The best time to automate was yesterday. The second best time is now.",
          author: "Conaugh McKenna",
        }}
      />
      <Composition
        id="CeoLog"
        component={CeoLog}
        durationInFrames={300}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          dayNumber: 47,
          headline: "Built 14 database tables in one night",
          body: "My AI agent now handles leads, email, bookings, revenue tracking, content scheduling — all zero new paid services.",
          metric: "$2,691 → $5,000 MRR",
        }}
      />
      <Composition
        id="SkoolIntro"
        component={SkoolIntro}
        durationInFrames={600}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
