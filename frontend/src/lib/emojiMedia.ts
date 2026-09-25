import api from "../services/api";

export type EmojiMeta = {
  custom_emoji_id: string;
  emoji: string;
  set_name: string;
  is_animated: boolean;
  is_video: boolean;
  format: "webm" | "lottie" | "image";
  width: number;
  height: number;
};

export type EmojiMedia = {
  url?: string;
  animationData?: object;
  error?: string;
};

const metaCache = new Map<string, EmojiMeta | null>();
const mediaCache = new Map<string, EmojiMedia>();
const metaWaiters = new Map<string, Array<(meta: EmojiMeta | null) => void>>();
let pendingIds: string[] = [];
let flushTimer: number | null = null;
let lastError = "";
let activeLoads = 0;
const loadQueue: Array<() => void> = [];

function schedule<T>(job: () => Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const run = () => {
      activeLoads += 1;
      job().then(resolve, reject).finally(() => {
        activeLoads -= 1;
        const next = loadQueue.shift();
        if (next) next();
      });
    };
    if (activeLoads < 4) run();
    else loadQueue.push(run);
  });
}

function settle(id: string, meta: EmojiMeta | null, remember: boolean) {
  if (remember) metaCache.set(id, meta);
  (metaWaiters.get(id) || []).forEach((resolve) => resolve(meta));
  metaWaiters.delete(id);
}

async function flushMeta() {
  flushTimer = null;
  const ids = [...new Set(pendingIds)].filter((id) => !metaCache.has(id));
  pendingIds = [];
  for (let offset = 0; offset < ids.length; offset += 200) {
    const chunk = ids.slice(offset, offset + 200);
    try {
      const { data } = await api.post("/api/emojis/previews", { custom_emoji_ids: chunk });
      lastError = data.error || lastError;
      const found = new Map<string, EmojiMeta>((data.items || []).map((item: EmojiMeta) => [item.custom_emoji_id, item]));
      const missing = new Set<string>(data.missing || []);
      for (const id of chunk) {
        if (found.has(id)) settle(id, found.get(id) || null, true);
        else if (missing.has(id)) settle(id, null, true);
        else settle(id, null, Boolean(data.error));
      }
    } catch (error: any) {
      lastError = error.response?.data?.detail || "پیش‌نمایش تلگرام خوانده نشد";
      for (const id of chunk) settle(id, null, false);
    }
  }
}

export function requestEmojiMeta(id: string): Promise<EmojiMeta | null> {
  if (!id) return Promise.resolve(null);
  if (metaCache.has(id)) return Promise.resolve(metaCache.get(id) ?? null);
  return new Promise((resolve) => {
    const waiters = metaWaiters.get(id) || [];
    waiters.push(resolve);
    metaWaiters.set(id, waiters);
    pendingIds.push(id);
    if (flushTimer == null) flushTimer = window.setTimeout(flushMeta, 40);
  });
}

export async function prefetchEmojiMeta(ids: string[]): Promise<string> {
  const unique = [...new Set(ids.filter(Boolean))];
  await Promise.all(unique.map((id) => requestEmojiMeta(id)));
  return lastError;
}

export function requestEmojiMedia(id: string, format: EmojiMeta["format"]): Promise<EmojiMedia> {
  const cached = mediaCache.get(id);
  if (cached) return Promise.resolve(cached);
  return schedule(async () => {
    const again = mediaCache.get(id);
    if (again) return again;
    try {
      if (format === "lottie") {
        const { data } = await api.get(`/api/emojis/media/${id}`, { responseType: "json" });
        const media = { animationData: data };
        mediaCache.set(id, media);
        return media;
      }
      const response = await api.get(`/api/emojis/media/${id}`, { responseType: "blob" });
      const blob = response.data as Blob;
      const typed = blob.type ? blob : new Blob([blob], { type: format === "webm" ? "video/webm" : "image/webp" });
      const media = { url: URL.createObjectURL(typed) };
      mediaCache.set(id, media);
      return media;
    } catch (error: any) {
      const media = { error: error.response?.data?.detail || "فایل تلگرام باز نشد" };
      mediaCache.set(id, media);
      return media;
    }
  });
}
