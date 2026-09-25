import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, GripVertical } from "lucide-react";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Page } from "../components/page";
import { useConfirm } from "@/components/ui/alert-dialog";
import { AsyncPage, LoadError } from "@/components/ui/page-state";
import { DefaultEmoji, EmojiPreview, useEmojiMeta } from "@/components/EmojiPreview";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, Input } from "@/components/ui/input";
import { SearchInput } from "@/components/ui/search-input";
import { Select } from "@/components/ui/select";
import { fa } from "@/lib/utils";

const SPECTRA = [
  ["news", "خبر"],
  ["announcement", "اطلاعیه"],
  ["fun", "فان"],
  ["guide", "راهنما"],
  ["alert", "هشدار"],
  ["consulting", "مشاوره"],
  ["general", "عمومی"],
] as const;

const ROLES = [
  ["divider", "جداکننده"],
  ["membership", "عضویت"],
  ["support", "پشتیبانی"],
] as const;

const ORDINALS = ["اول", "دوم", "سوم", "چهارم", "پنجم", "ششم", "هفتم", "هشتم", "نهم", "دهم", "یازدهم", "دوازدهم", "سیزدهم", "چهاردهم", "پانزدهم", "شانزدهم", "هفدهم", "هجدهم", "نوزدهم", "بیستم"];

function spectrumLabel(value: string | null | undefined) {
  return [...SPECTRA, ...ROLES].find(([key]) => key === value)?.[1] || "بدون طیف";
}

function bucketOf(item: { bucket?: string | null; category?: string | null }) {
  return item.bucket || item.category || "";
}

function rankLabel(rank: number) {
  if (rank >= 1 && rank <= ORDINALS.length) return `اولویت ${ORDINALS[rank - 1]}`;
  return `اولویت ${fa(rank)}`;
}

function idsOf(items: any[], bucket: string) {
  return items
    .filter((item) => bucketOf(item) === bucket)
    .sort((a, b) => (a.rank || 0) - (b.rank || 0) || String(a.id).localeCompare(String(b.id)))
    .map((item) => item.id);
}

function moveToIndex(items: any[], bucket: string, fromId: string, insertAt: number) {
  const ids = idsOf(items, bucket);
  const from = ids.indexOf(fromId);
  if (from < 0) return items;
  const nextIds = ids.filter((id) => id !== fromId);
  const at = Math.max(0, Math.min(insertAt, nextIds.length));
  if (at === from) return items;
  nextIds.splice(at, 0, fromId);
  const rank = new Map(nextIds.map((id, index) => [id, index + 1]));
  const priority = new Map(nextIds.map((id, index) => [id, nextIds.length - index]));
  return items.map((item) => (
    rank.has(item.id) ? { ...item, rank: rank.get(item.id), priority: priority.get(item.id) } : item
  ));
}

function indexAt(bucket: string, dragId: string, clientY: number) {
  const cards = Array.from(document.querySelectorAll<HTMLElement>(`[data-bucket="${CSS.escape(bucket)}"][data-emoji-id]`));
  const others = cards.filter((card) => card.dataset.emojiId !== dragId);
  if (!others.length) return 0;
  for (let index = 0; index < others.length; index += 1) {
    const rect = others[index].getBoundingClientRect();
    if (clientY < rect.top + rect.height / 2) return index;
  }
  return others.length;
}

export default function Emojis() {
  const role = useAuth((state) => state.role);
  const canEdit = !role || role !== "VIEWER";
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ unicode_emoji: "", custom_emoji_id: "", category: "" });
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState<any>(null);
  const [zoom, setZoom] = useState<any>(null);
  const [packUrl, setPackUrl] = useState("");
  const [packBusy, setPackBusy] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [spectrum, setSpectrum] = useState("");
  const [classifyBusy, setClassifyBusy] = useState(false);
  const [bulkCategory, setBulkCategory] = useState("");
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [dragId, setDragId] = useState("");
  const dragRef = useRef<{ id: string; bucket: string; ids: string[]; dirty: boolean; insertAt: number } | null>(null);
  const frames = useRef<Map<string, number>>(new Map());
  const stopDrag = useRef<(() => void) | null>(null);
  const { ask, dialog } = useConfirm();
  const canReorder = canEdit && !q.trim();

  async function load() {
    try {
      setItems((await api.get("/api/emojis", { timeout: 12000 })).data);
      setLoadError("");
    } catch (error: any) {
      setLoadError(error.response?.data?.detail || "ایموجی‌ها خوانده نشد");
    } finally {
      setReady(true);
    }
  }
  useEffect(() => { load(); }, []);

  const shown = items.filter((item) => (!spectrum || bucketOf(item) === spectrum) && (!q || `${item.unicode_emoji} ${item.custom_emoji_id} ${item.category || ""} ${item.label || ""}`.includes(q)));
  const selectedSet = new Set(selected);
  const sections = [...SPECTRA, ...ROLES, ["", "بدون طیف"] as const].filter(([key]) => !spectrum || key === spectrum);

  function toggleSelected(id: string, on: boolean) {
    setSelected((prev) => on ? [...new Set([...prev, id])] : prev.filter((item) => item !== id));
  }

  async function saveOrder(bucket: string, ids: string[]) {
    try {
      const { data } = await api.post("/api/emojis/reorder", { category: bucket, ids });
      const incoming = new Map((data.items || []).map((item: any) => [item.id, item]));
      setItems((prev) => prev.map((item) => incoming.get(item.id) || item));
      setMsg("ترتیب این طیف ذخیره شد");
    } catch (error: any) {
      setMsg(error.response?.data?.detail || "ترتیب ذخیره نشد");
      await load();
    }
  }

  function captureFrames() {
    document.querySelectorAll<HTMLElement>("[data-emoji-id]").forEach((node) => {
      frames.current.set(node.dataset.emojiId || "", node.getBoundingClientRect().top);
    });
  }

  function placeCard(bucket: string, fromId: string, insertAt: number) {
    let ids: string[] = [];
    captureFrames();
    setItems((prev) => {
      const next = moveToIndex(prev, bucket, fromId, insertAt);
      ids = idsOf(next, bucket);
      if (dragRef.current) {
        dragRef.current.dirty = dragRef.current.dirty || ids.join() !== dragRef.current.ids.join();
        dragRef.current.ids = ids;
        dragRef.current.insertAt = insertAt;
      }
      return next;
    });
    return ids;
  }

  function step(item: any, direction: -1 | 1) {
    const bucket = bucketOf(item);
    const ids = idsOf(items, bucket);
    const index = ids.indexOf(item.id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const next = placeCard(bucket, item.id, target);
    void saveOrder(bucket, next);
  }

  function finishDrag() {
    stopDrag.current?.();
    stopDrag.current = null;
    const drag = dragRef.current;
    dragRef.current = null;
    setDragId("");
    document.body.style.userSelect = "";
    if (drag?.dirty) void saveOrder(drag.bucket, drag.ids);
  }

  function onHandleDown(event: React.PointerEvent<HTMLButtonElement>, item: any) {
    if (!canReorder) return;
    event.stopPropagation();
    event.preventDefault();
    const bucket = bucketOf(item);
    captureFrames();
    dragRef.current = { id: item.id, bucket, ids: idsOf(items, bucket), dirty: false, insertAt: idsOf(items, bucket).indexOf(item.id) };
    setDragId(item.id);
    document.body.style.userSelect = "none";
    const move = (pointer: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      pointer.preventDefault();
      const insertAt = indexAt(drag.bucket, drag.id, pointer.clientY);
      if (insertAt === drag.insertAt) return;
      placeCard(drag.bucket, drag.id, insertAt);
    };
    const up = () => finishDrag();
    window.addEventListener("pointermove", move, { passive: false });
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    stopDrag.current = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  }

  useLayoutEffect(() => {
    document.querySelectorAll<HTMLElement>("[data-emoji-id]").forEach((node) => {
      const id = node.dataset.emojiId || "";
      const prev = frames.current.get(id);
      const next = node.getBoundingClientRect().top;
      frames.current.set(id, next);
      if (prev == null || Math.abs(prev - next) < 2) return;
      node.animate(
        [{ transform: `translateY(${prev - next}px)` }, { transform: "translateY(0)" }],
        { duration: 220, easing: "cubic-bezier(.2,.8,.2,1)" },
      );
    });
  }, [items]);

  useEffect(() => () => stopDrag.current?.(), []);

  async function classify(force = false) {
    setClassifyBusy(true);
    let changed = 0;
    let left = 0;
    let open = 0;
    let by = "none";
    try {
      let after = "";
      for (let round = 0; round < (force ? 1 : 40); round += 1) {
        const { data } = await api.post("/api/emojis/classify", force ? { ids: selected, force: true } : { after_id: after }, { timeout: 90000 });
        changed += data.changed || 0;
        left = data.left || 0;
        open = data.open || 0;
        after = data.after_id || after;
        if (data.by && data.by !== "none") by = data.by;
        if (!force) setMsg(`اسکن کتابخانه… ${fa(changed)} طبقه شد${left ? ` · ${fa(left)} مانده` : ""}`);
        if (force || !left) break;
      }
      await load();
      setMsg(force
        ? `انتخاب‌شده‌ها دوباره طبقه شد: ${fa(changed)}`
        : `کل کتابخانه اسکن شد. ${fa(changed)} بدون طیف طبقه شد و رفتند ته صف همان طیف. طیف‌دارها دست نخوردند.${open ? ` ${fa(open)} تا هنوز شکل مشخصی برای طیف نداشت.` : ""}`);
    } catch (error: any) {
      setMsg(error.response?.data?.detail || "طبقه‌بندی انجام نشد");
    } finally {
      setClassifyBusy(false);
    }
  }

  async function bulk(action: string, extra: Record<string, unknown> = {}) {
    if (!selected.length) return;
    if (action === "delete") {
      ask(`${fa(selected.length)} ایموجی حذف شود؟`, () => bulkNow(action, extra));
      return;
    }
    await bulkNow(action, extra);
  }

  async function bulkNow(action: string, extra: Record<string, unknown> = {}) {
    try {
      let count = 0;
      for (let index = 0; index < selected.length; index += 500) {
        const { data } = await api.post("/api/emojis/bulk", { ids: selected.slice(index, index + 500), action, ...extra });
        count += data.count ?? 0;
      }
      setMsg(`اعمال شد: ${fa(count)}`);
      setSelected([]);
      await load();
    } catch (error: any) {
      setMsg(error.response?.data?.detail || "کار گروهی انجام نشد");
    }
  }

  if (!ready) {
    return <AsyncPage kicker="کتابخانه متحرک" title="ایموجی پرمیوم" description="نگاشت ایموجی متحرک از همین کتابخانه خوانده می‌شود." loading skeleton="form" />;
  }

  return (
    <Page
      kicker="کتابخانه متحرک"
      title="ایموجی پرمیوم"
      description="هر طیف یک صف است. کارت را بکش تا جایش عوض شود. اولویت اول، اولین ایموجی همان طیف در پست خودکار است."
      actions={<Button variant="outline" onClick={async () => { const { data } = await api.get("/api/emojis/export"); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "khoshgelasion-emojis.json"; a.click(); }}>خروجی</Button>}
    >
      {dialog}
      {loadError && <LoadError title={loadError} onRetry={load} />}
      <Alert title="ترتیب، نه عدد">
        در هر طیف کارت‌ها از اولویت اول تا آخر چیده شده‌اند. دسته را بکش؛ خط چین جای نشستن را نشان می‌دهد و کارت همان‌جا می‌لغزد. پست خودکار از اولویت اول شروع می‌کند. ایموجی تازه ته صف می‌ایستد. خاموش‌ها در صف می‌مانند ولی در پست استفاده نمی‌شوند.
      </Alert>
      <Card>
        <CardHeader><CardTitle>ورود از لینک پک</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Field label="لینک یا نام پک"><Input dir="ltr" value={packUrl} onChange={(e) => setPackUrl(e.target.value)} placeholder="https://t.me/addemoji/Name" /></Field>
          <Button variant="brand" disabled={!canEdit || packBusy || !packUrl.trim()} onClick={async () => {
            setPackBusy(true);
            try {
              const { data } = await api.post("/api/emojis/import-pack", { url: packUrl.trim() });
              setMsg(data.message || `اضافه شد: ${data.imported ?? 0}`);
              setPackUrl("");
              load();
            } catch (error: any) { setMsg(error.response?.data?.detail || "پک خوانده نشد"); }
            finally { setPackBusy(false); }
          }}>{packBusy ? "در حال خواندن" : "خواندن پک"}</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>نگاشت تازه</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="ایموجی"><Input value={form.unicode_emoji} onChange={(e) => setForm({ ...form, unicode_emoji: e.target.value })} /></Field>
            <Field label="custom_emoji_id"><Input dir="ltr" value={form.custom_emoji_id} onChange={(e) => setForm({ ...form, custom_emoji_id: e.target.value })} /></Field>
            <Field label="طیف"><Select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} options={[{ value: "", label: "بدون طیف" }, ...SPECTRA.map(([value, label]) => ({ value, label }))]} /></Field>
          </div>
          <Button variant="brand" disabled={!canEdit} onClick={async () => {
            try {
              await api.post("/api/emojis", { ...form, category: form.category || undefined });
              setForm({ unicode_emoji: "", custom_emoji_id: "", category: "" });
              setMsg("اضافه شد و رفت ته صف همین طیف");
              load();
            } catch (error: any) { setMsg(error.response?.data?.detail || "ثبت نشد"); }
          }}>افزودن</Button>
          {msg && <Alert>{msg}</Alert>}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-full max-w-xs"><SearchInput value={q} onChange={setQ} placeholder="جست‌وجوی ایموجی یا ID" /></div>
        <Select className="h-9 w-36" value={spectrum} onChange={(event) => setSpectrum(event.target.value)} options={[{ value: "", label: "همه طیف‌ها" }, ...SPECTRA.map(([value, label]) => ({ value, label })), ...ROLES.map(([value, label]) => ({ value, label }))]} />
        <Button variant="brand" disabled={!canEdit || classifyBusy} onClick={() => classify(false)}>{classifyBusy ? "در حال اسکن کتابخانه…" : "طبقه‌بندی با هوش مصنوعی"}</Button>
        {canEdit && <Button variant="outline" onClick={() => setSelected(shown.map((item) => item.id))}>انتخاب همین فهرست</Button>}
        {canEdit && selected.length > 0 && <Button variant="outline" onClick={() => setSelected([])}>لغو انتخاب</Button>}
      </div>
      {q.trim() && <p className="text-xs text-muted-foreground">جست‌وجو روشن است. برای جابه‌جایی کارت‌ها، جست‌وجو را خالی کن تا ترتیب طیف به هم نریزد.</p>}
      {canEdit && selected.length > 0 && (
        <div className="sticky top-2 z-10 flex flex-wrap items-end gap-2 rounded-2xl border border-border bg-card p-3">
          <p className="self-center text-sm">{fa(selected.length)} انتخاب شده</p>
          <Button size="sm" variant="destructive" onClick={() => bulk("delete")}>حذف گروهی</Button>
          <Button size="sm" variant="outline" onClick={() => bulk("disable")}>خاموش گروهی</Button>
          <Button size="sm" variant="outline" onClick={() => bulk("enable")}>روشن گروهی</Button>
          <Select className="h-8 w-32" value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)} options={[{ value: "", label: "طیف دستی" }, ...SPECTRA.map(([value, label]) => ({ value, label }))]} />
          <Button size="sm" variant="outline" onClick={() => bulk("category", { category: bulkCategory })}>اعمال طیف دستی</Button>
        </div>
      )}

      {shown.length ? (
        <div className="space-y-8">
          {sections.map(([key, label]) => {
            const queue = shown
              .filter((item) => bucketOf(item) === key)
              .sort((a, b) => (a.rank || 0) - (b.rank || 0) || String(a.id).localeCompare(String(b.id)));
            if (!queue.length) return null;
            return (
              <section key={key || "none"} className="space-y-3">
                <div>
                  <h2 className="text-base font-semibold">{label}</h2>
                  <p className="text-xs text-muted-foreground">{fa(queue.length)} ایموجی، از اولویت اول تا آخر</p>
                </div>
                <div className="grid gap-3">
                  {queue.map((item) => (
                    <div key={item.id} className="relative">
                      {dragId === item.id && (
                        <div className="pointer-events-none absolute inset-x-0 bottom-full z-30 mb-1 flex items-center gap-2 rounded-xl border border-dashed border-brand bg-brand/10 px-3 py-1.5 text-xs font-medium text-brand" aria-live="polite">
                          <span className="inline-block size-2 rounded-full bg-brand" />
                          اینجا می‌نشیند · {rankLabel(Number(item.rank || 1))}
                        </div>
                      )}
                    <EmojiCard
                      key={item.id}
                      item={item}
                      rank={Number(item.rank || 0)}
                      canEdit={canEdit}
                      canReorder={canReorder}
                      dragging={dragId === item.id}
                      selected={selectedSet.has(item.id)}
                      onSelect={(on) => toggleSelected(item.id, on)}
                      onZoom={() => setZoom(item)}
                      onEdit={() => setEdit({ ...item })}
                      onToggle={async () => { await api.patch(`/api/emojis/${item.id}`, { enabled: !item.enabled }); load(); }}
                      onDelete={() => ask("این نگاشت حذف شود؟", async () => { await api.delete(`/api/emojis/${item.id}`); load(); })}
                      onSpectrum={async (value) => { await api.patch(`/api/emojis/${item.id}`, { category: value || null }); load(); }}
                      onAdopt={async () => {
                        try {
                          await api.post(`/api/emojis/${item.id}/telegram-fallback`);
                          setMsg("پیش‌فرض تلگرام روی نگاشت ذخیره شد");
                          load();
                        } catch (error: any) { setMsg(error.response?.data?.detail || "پیش‌فرض اعمال نشد"); }
                      }}
                      onStep={(direction) => step(item, direction)}
                      onHandleDown={(event) => onHandleDown(event, item)}
                    />
                    </div>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : loadError ? null : <EmptyState title="نگاشتی نیست" description="یک ایموجی پرمیوم را به ربات فوروارد کن." />}

      <Dialog open={!!edit} onOpenChange={(open) => !open && setEdit(null)} title="ویرایش نگاشت">
        {edit && (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <EmojiPreview id={edit.custom_emoji_id} size={96} />
              <DefaultEmoji value={edit.unicode_emoji} size={42} />
            </div>
            <Field label="ایموجی"><Input value={edit.unicode_emoji} onChange={(e) => setEdit({ ...edit, unicode_emoji: e.target.value })} /></Field>
            <Field label="custom_emoji_id"><Input dir="ltr" value={edit.custom_emoji_id} onChange={(e) => setEdit({ ...edit, custom_emoji_id: e.target.value })} /></Field>
            <Field label="طیف"><Select value={edit.category || ""} onChange={(e) => setEdit({ ...edit, category: e.target.value })} options={[{ value: "", label: "بدون طیف" }, ...SPECTRA.map(([value, label]) => ({ value, label })), ...ROLES.map(([value, label]) => ({ value, label }))]} /></Field>
            <p className="text-xs text-muted-foreground">جای این کارت در صف، با کشیدن خودش در فهرست عوض می‌شود، نه با عدد.</p>
            <Button variant="brand" disabled={!canEdit} onClick={async () => {
              try {
                await api.patch(`/api/emojis/${edit.id}`, { unicode_emoji: edit.unicode_emoji, custom_emoji_id: edit.custom_emoji_id, category: edit.category || null });
                setEdit(null);
                setMsg("نگاشت ذخیره شد");
                load();
              } catch (error: any) { setMsg(error.response?.data?.detail || "ذخیره نشد"); }
            }}>ذخیره</Button>
          </div>
        )}
      </Dialog>
      <Dialog open={!!zoom} onOpenChange={(open) => !open && setZoom(null)} size="lg" title="پیش‌نمایش تلگرام" description="فایل متحرک از getCustomEmojiStickers و getFile است. ایموجی معمولی، فیلد emoji همان استیکر است.">
        {zoom && (
          <div className="flex flex-col items-center gap-4 py-2">
            <EmojiPreview id={zoom.custom_emoji_id} size={180} fallback={zoom.unicode_emoji} />
            <ZoomFallback id={zoom.custom_emoji_id} stored={zoom.unicode_emoji} />
            <p className="text-xs text-muted-foreground" dir="ltr">{zoom.custom_emoji_id}</p>
          </div>
        )}
      </Dialog>
    </Page>
  );
}

function EmojiCard({ item, rank, canEdit, canReorder, dragging, selected, onSelect, onZoom, onEdit, onToggle, onDelete, onAdopt, onSpectrum, onStep, onHandleDown }: {
  item: any;
  rank: number;
  canEdit: boolean;
  canReorder: boolean;
  dragging: boolean;
  selected: boolean;
  onSelect: (on: boolean) => void;
  onZoom: () => void;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: () => void;
  onAdopt: () => void;
  onSpectrum: (value: string) => void;
  onStep: (direction: -1 | 1) => void;
  onHandleDown: (event: React.PointerEvent<HTMLButtonElement>) => void;
}) {
  const meta = useEmojiMeta(item.custom_emoji_id);
  const seen = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const node = seen.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: "240px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const telegramEmoji = meta?.emoji || "";
  const differs = Boolean(telegramEmoji && telegramEmoji !== item.unicode_emoji);
  return (
    <Card
      data-emoji-id={item.id}
      data-bucket={bucketOf(item)}
      role={canEdit ? "button" : undefined}
      tabIndex={canEdit ? 0 : undefined}
      aria-pressed={canEdit ? selected : undefined}
      onClick={() => { if (canEdit) onSelect(!selected); }}
      onKeyDown={(event) => {
        if (!canEdit || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        onSelect(!selected);
      }}
      className={selected ? "relative cursor-pointer ring-2 ring-brand" : dragging ? "relative z-20 cursor-grabbing shadow-xl ring-2 ring-brand" : "relative cursor-pointer"}
    >
      <span className="absolute top-3 end-3 rounded-full border border-border bg-card px-2 py-0.5 text-[11px] font-medium text-brand">{rank ? rankLabel(rank) : "بدون نوبت"}</span>
      <CardContent className="space-y-3 p-4 pe-28">
        <div ref={seen} className="flex items-center gap-3">
          {canReorder && (
            <button
              type="button"
              className="cursor-grab touch-none rounded-lg border border-border p-1 text-muted-foreground"
              aria-label="جابه‌جایی در صف"
              onPointerDown={onHandleDown}
              onClick={(event) => event.stopPropagation()}
            >
              <GripVertical className="size-4" />
            </button>
          )}
          {canEdit && <span onClick={(event) => event.stopPropagation()}><Checkbox checked={selected} onCheckedChange={onSelect} aria-label="انتخاب" /></span>}
          <button type="button" onClick={(event) => { event.stopPropagation(); onZoom(); }} className="cursor-pointer rounded-2xl" aria-label="بزرگ‌نمایی">
            <EmojiPreview id={item.custom_emoji_id} size={76} active={visible} fallback={item.unicode_emoji} />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <DefaultEmoji value={telegramEmoji || item.unicode_emoji} size={36} />
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground">{meta?.is_video || meta?.is_animated ? "پرمیوم متحرک" : "پرمیوم"} · پیش‌فرض</p>
                <p className="truncate text-xs" dir="ltr">{meta?.set_name || item.label || item.source || ""}</p>
              </div>
            </div>
            {differs && <p className="mt-1 text-[11px] text-muted-foreground">جایگزینی در پست: {item.unicode_emoji}</p>}
            <p className="mt-1 truncate text-[11px] text-muted-foreground" dir="ltr">{item.custom_emoji_id}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={item.enabled ? "success" : "secondary"}>{item.enabled ? "فعال" : "خاموش"}</Badge>
          {item.custom_emoji_id?.startsWith("53683241") && <Badge variant="warning">فیک</Badge>}
          <Badge variant="secondary">{spectrumLabel(item.category)}{item.source === "manual" ? " · دستی" : item.source === "ai" ? " · هوش مصنوعی" : ""}</Badge>
          <span className="text-xs text-muted-foreground">استفاده {fa(item.usage_count || 0)}</span>
        </div>
        {canEdit && <span onClick={(event) => event.stopPropagation()}><Select className="h-8" value={item.category || ""} onChange={(event) => onSpectrum(event.target.value)} options={[{ value: "", label: "بدون طیف" }, ...SPECTRA.map(([value, label]) => ({ value, label })), ...ROLES.map(([value, label]) => ({ value, label }))]} /></span>}
        <div className="flex flex-wrap gap-2" onClick={(event) => event.stopPropagation()}>
          {canReorder && <Button size="sm" variant="outline" aria-label="یک پله بالاتر" onClick={() => onStep(-1)}><ChevronUp className="size-4" /></Button>}
          {canReorder && <Button size="sm" variant="outline" aria-label="یک پله پایین‌تر" onClick={() => onStep(1)}><ChevronDown className="size-4" /></Button>}
          <Button size="sm" variant="outline" disabled={!canEdit} onClick={onEdit}>ویرایش</Button>
          <Button size="sm" variant="outline" disabled={!canEdit} onClick={onToggle}>{item.enabled ? "خاموش" : "روشن"}</Button>
          {differs && <Button size="sm" variant="outline" disabled={!canEdit} onClick={onAdopt}>پیش‌فرض تلگرام</Button>}
          <Button size="sm" variant="destructive" disabled={!canEdit} onClick={onDelete}>حذف</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ZoomFallback({ id, stored }: { id: string; stored: string }) {
  const meta = useEmojiMeta(id);
  const glyph = meta?.emoji || stored;
  return (
    <div className="text-center">
      <DefaultEmoji value={glyph} size={52} />
      <p className="text-xs text-muted-foreground">{meta?.emoji ? "پیش‌فرض تلگرام" : "پیش‌فرض ذخیره‌شده"}{meta?.emoji && meta.emoji !== stored ? ` · جایگزینی فعلی: ${stored}` : ""}</p>
    </div>
  );
}
