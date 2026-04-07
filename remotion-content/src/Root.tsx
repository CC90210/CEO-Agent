import React from "react";
import { Composition } from "remotion";
import { QuoteCard, QuoteCardProps } from "./compositions/QuoteCard";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="QuoteCard"
        component={QuoteCard}
        durationInFrames={150}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={
          {
            quote:
              "The best business advice I ever got wasn't about business.",
            author: "Conaugh McKenna",
            pillar: "quote_drop",
          } satisfies QuoteCardProps
        }
      />
    </>
  );
};
