import { useEffect, useRef, useState } from "react";
import { EmojiMeta, requestEmojiMedia, requestEmojiMeta } from "@/lib/emojiMedia";

const EMOJI_FONT = '"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", emoji, sans-serif';

export function useEmojiMeta(id: string) {
  const [meta, setMeta] = useState<EmojiMeta | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    setMeta(undefined);
    requestEmojiMeta(id).then((item) => {
      if (live) setMeta(item);
    });
    return () => {
      live = false;
    };
  }, [id]);
  return meta;
}

export function DefaultEmoji({ value, size = 40 }: { value: string; size?: number }) {
  return (
    <span
      className="inline-flex items-center justify-center leading-none"
      style={{ fontFamily: EMOJI_FONT, fontSize: size, width: size + 8, height: size + 8 }}
      aria-hidden={!value}
    >
      {value || "·"}
    </span>
  );
}

export function EmojiPreview({ id, size = 72, active = true, fallback = "" }: { id: string; size?: number; active?: boolean; fallback?: string }) {
  const meta = useEmojiMeta(id);
  const box = useRef<HTMLDivElement>(null);
  const [media, setMedia] = useState<{ url?: string; animationData?: object; error?: string } | null>(null);
  const reduceMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    if (!active || !meta) return;
    let live = true;
    requestEmojiMedia(id, meta.format).then((item) => {
      if (live) setMedia(item);
    });
    return () => {
      live = false;
    };
  }, [active, id, meta]);

  useEffect(() => {
    if (!active || !box.current || !media?.animationData) return;
    let anim: { destroy: () => void } | null = null;
    let cancelled = false;
    import("lottie-web/build/player/lottie_light").then((mod) => {
      if (cancelled || !box.current) return;
      const lottie = mod.default;
      anim = lottie.loadAnimation({
        container: box.current,
        renderer: "svg",
        loop: !reduceMotion,
        autoplay: !reduceMotion,
        animationData: media.animationData,
      });
    }).catch(() => undefined);
    return () => {
      cancelled = true;
      anim?.destroy();
    };
  }, [active, media, reduceMotion]);

  return (
    <div
      className="flex shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-border bg-background/70"
      style={{ width: size, height: size }}
      aria-label="پیش‌نمایش ایموجی پرمیوم"
    >
      {active && media?.url && meta?.format === "webm" && (
        <video
          src={media.url}
          autoPlay={!reduceMotion}
          loop={!reduceMotion}
          muted
          playsInline
          className="h-full w-full object-contain"
        />
      )}
      {active && media?.url && meta?.format === "image" && (
        <img src={media.url} alt="" className="h-full w-full object-contain" />
      )}
      {active && meta?.format === "lottie" && <div ref={box} className="h-full w-full" />}
      {meta === null && (fallback ? <DefaultEmoji value={fallback} size={Math.round(size * 0.55)} /> : <span className="text-[10px] text-muted-foreground">نیست</span>)}
      {meta === undefined && <span className="size-4 animate-pulse rounded-full bg-muted" />}
      {media?.error && <span className="px-1 text-center text-[10px] text-muted-foreground">باز نشد</span>}
    </div>
  );
}
