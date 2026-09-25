import { useEffect, useRef, useState } from "react";
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
import { prefetchEmojiMeta } from "@/lib/emojiMedia";
import { en, fa } from "@/lib/utils";

const SPECTRA = [
  ["news", "خبر"],
  ["announcement", "اطلاعیه"],
  ["fun", "فان"],
  ["guide", "راهنما"],
  ["alert", "هشدار"],
  ["consulting", "مشاوره"],
  ["general", "عمومی"],
] as const;

function spectrumLabel(value: string | null | undefined) {
  return SPECTRA.find(([key]) => key === value)?.[1] || "بدون طیف";
}

function readPriority(value: unknown): number | null {
  const parsed = Number(en(String(value ?? "").trim()));
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 1000) return null;
  return parsed;
}

export default function Emojis() {
  const role = useAuth((state) => state.role);
  const canEdit = !role || role !== "VIEWER";
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "70" });
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
  const [bulkPriority, setBulkPriority] = useState("70");
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState("");
  const { ask, dialog } = useConfirm();

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
  useEffect(() => {
    const ids = items.map((item) => item.custom_emoji_id).filter(Boolean);
    if (!ids.length) return;
    let cancelled = false;
    const chunks: string[][] = [];
    for (let offset = 0; offset < ids.length; offset += 36) chunks.push(ids.slice(offset, offset + 36));
    (async () => {
      for (const chunk of chunks) {
        if (cancelled) return;
        const error = await prefetchEmojiMeta(chunk);
        if (error) setMsg(error);
        await new Promise((resolve) => window.setTimeout(resolve, 400));
      }
    })().catch(() => {});
    return () => { cancelled = true; };
  }, [items]);
  const shown = items.filter((item) => (!spectrum || item.category === spectrum) && (!q || `${item.unicode_emoji} ${item.custom_emoji_id} ${item.category || ""}`.includes(q)));
  const selectedSet = new Set(selected);

  function toggleSelected(id: string, on: boolean) {
    setSelected((prev) => on ? [...new Set([...prev, id])] : prev.filter((item) => item !== id));
  }

  async function classify(force = false) {
    setClassifyBusy(true);
    try {
      const { data } = await api.post("/api/emojis/classify", { ids: selected.length ? selected : undefined, force }, { timeout: 70000 });
      const how = data.by === "ai" ? "هوش مصنوعی" : data.by === "guess" ? "حدس از شکل، چون مدل آماده نبود" : "بدون تغییر";
      setMsg(`طبقه‌بندی: ${fa(data.changed || 0)} · ${how}${data.skipped_manual ? ` · ${fa(data.skipped_manual)} اصلاح دستی ماند` : ""}`);
      await load();
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
      description="هوش مصنوعی طیف را می‌گذارد. اگر اشتباه بود، خودت عوضش کن؛ اصلاح دستی تا وقتی دوباره نخواهی پاک نمی‌شود."
      actions={<Button variant="outline" onClick={async () => { const { data } = await api.get("/api/emojis/export"); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "khoshgelasion-emojis.json"; a.click(); }}>خروجی</Button>}
    >
      {dialog}
      {loadError && <LoadError title={loadError} onRetry={load} />}
      <Alert title="کتابخانه از خود تلگرام پر می‌شود">
        لینک https://t.me/addemoji/نام‌پک را اینجا یا در خصوصی ربات بفرست. تصویر متحرک هر کارت از getCustomEmojiStickers و getFile تلگرام می‌آید و توکن ربات در مرورگر نیست. کنارش ایموجی معمولی همان استیکر است؛ Bot API برای ایموجی معمولی فایل متحرک جدا ندارد.
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
          <div className="grid gap-3 md:grid-cols-4">
            <Field label="ایموجی"><Input value={form.unicode_emoji} onChange={(e) => setForm({ ...form, unicode_emoji: e.target.value })} /></Field>
            <Field label="custom_emoji_id"><Input dir="ltr" value={form.custom_emoji_id} onChange={(e) => setForm({ ...form, custom_emoji_id: e.target.value })} /></Field>
            <Field label="طیف"><Select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} options={[{ value: "", label: "بدون طیف" }, ...SPECTRA.map(([value, label]) => ({ value, label }))]} /></Field>
            <Field label="اولویت"><Input value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} /></Field>
          </div>
          <Button variant="brand" disabled={!canEdit} onClick={async () => {
            try {
              const priority = readPriority(form.priority);
              if (priority === null) throw new Error("priority");
              await api.post("/api/emojis", { ...form, priority, category: form.category || undefined });
              setForm({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "70" });
              setMsg("اضافه شد");
              load();
            } catch (error: any) { setMsg(error.response?.data?.detail || (error.message === "priority" ? "اولویت باید عدد ۰ تا ۱۰۰۰ باشد" : "ثبت نشد")); }
          }}>افزودن</Button>
          {msg && <Alert>{msg}</Alert>}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-full max-w-xs"><SearchInput value={q} onChange={setQ} placeholder="جست‌وجوی ایموجی یا ID" /></div>
        <Select className="h-9 w-36" value={spectrum} onChange={(event) => setSpectrum(event.target.value)} options={[{ value: "", label: "همه طیف‌ها" }, ...SPECTRA.map(([value, label]) => ({ value, label }))]} />
        <Button variant="brand" disabled={!canEdit || classifyBusy} onClick={() => classify(false)}>{classifyBusy ? "در حال طبقه‌بندی…" : "طبقه‌بندی با هوش مصنوعی"}</Button>
        {canEdit && selected.length > 0 && <Button variant="outline" disabled={classifyBusy} onClick={() => classify(true)}>دوباره، حتی اصلاح دستی</Button>}
        <Button variant="outline" onClick={async () => { const ids = shown.slice(0, 20).map((item) => item.custom_emoji_id); const { data } = await api.post("/api/emojis/validate", { custom_emoji_ids: ids }); setMsg(`معتبر: ${data.valid?.length || 0} / نامعتبر: ${data.invalid?.length || 0}${data.error ? " · " + data.error : ""}`); }}>اعتبارسنجی ۲۰ تای اول</Button>
        <Button variant="outline" disabled={!canEdit} onClick={async () => { await api.post("/api/emojis/cleanup-fake"); load(); }}>حذف IDهای فیک</Button>
        {canEdit && <Button variant="outline" onClick={() => setSelected(shown.map((item) => item.id))}>انتخاب همین فهرست</Button>}
        {canEdit && <Button variant="outline" onClick={() => setSelected(items.filter((item) => item.custom_emoji_id?.startsWith("53683241")).map((item) => item.id))}>انتخاب فیک‌ها</Button>}
        {canEdit && selected.length > 0 && <Button variant="outline" onClick={() => setSelected([])}>لغو انتخاب</Button>}
      </div>
      {canEdit && selected.length > 0 && (
        <div className="sticky top-2 z-10 flex flex-wrap items-end gap-2 rounded-2xl border border-border bg-card p-3">
          <p className="self-center text-sm">{fa(selected.length)} انتخاب شده</p>
          <Button size="sm" variant="destructive" onClick={() => bulk("delete")}>حذف گروهی</Button>
          <Button size="sm" variant="outline" onClick={() => bulk("disable")}>خاموش گروهی</Button>
          <Button size="sm" variant="outline" onClick={() => bulk("enable")}>روشن گروهی</Button>
          <Select className="h-8 w-32" value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)} options={[{ value: "", label: "طیف دستی" }, ...SPECTRA.map(([value, label]) => ({ value, label }))]} />
          <Button size="sm" variant="outline" onClick={() => bulk("category", { category: bulkCategory })}>اعمال طیف دستی</Button>
          <Input className="h-8 w-20" type="number" value={bulkPriority} onChange={(event) => setBulkPriority(event.target.value)} />
          <Button size="sm" variant="outline" onClick={() => { const priority = readPriority(bulkPriority); if (priority === null) { setMsg("اولویت باید عدد ۰ تا ۱۰۰۰ باشد"); return; } bulk("priority", { priority }); }}>اعمال اولویت</Button>
        </div>
      )}

      {shown.length ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((item) => (
            <EmojiCard
              key={item.id}
              item={item}
              canEdit={canEdit}
              selected={selectedSet.has(item.id)}
              onSelect={(on) => toggleSelected(item.id, on)}
              onZoom={() => setZoom(item)}
              onEdit={() => setEdit({ ...item, priority: String(item.priority ?? 50) })}
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
            />
          ))}
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
            <Field label="طیف"><Select value={edit.category || ""} onChange={(e) => setEdit({ ...edit, category: e.target.value })} options={[{ value: "", label: "بدون طیف" }, ...SPECTRA.map(([value, label]) => ({ value, label }))]} /></Field>
            <Field label="اولویت"><Input inputMode="numeric" value={edit.priority} onChange={(e) => setEdit({ ...edit, priority: e.target.value })} /></Field>
            <Button variant="brand" disabled={!canEdit} onClick={async () => {
              const priority = readPriority(edit.priority);
              if (priority === null) { setMsg("اولویت باید عدد ۰ تا ۱۰۰۰ باشد"); return; }
              try {
                await api.patch(`/api/emojis/${edit.id}`, { unicode_emoji: edit.unicode_emoji, custom_emoji_id: edit.custom_emoji_id, category: edit.category || null, priority });
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

function EmojiCard({ item, canEdit, selected, onSelect, onZoom, onEdit, onToggle, onDelete, onAdopt, onSpectrum }: {
  item: any;
  canEdit: boolean;
  selected: boolean;
  onSelect: (on: boolean) => void;
  onZoom: () => void;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: () => void;
  onAdopt: () => void;
  onSpectrum: (value: string) => void;
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
    <Card>
      <CardContent className="space-y-3 p-4">
        <div ref={seen} className="flex items-center gap-3">
          {canEdit && <Checkbox checked={selected} onCheckedChange={onSelect} aria-label="انتخاب" />}
          <button type="button" onClick={onZoom} className="cursor-pointer rounded-2xl" aria-label="بزرگ‌نمایی">
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
          <span className="text-xs text-muted-foreground">اولویت {fa(item.priority ?? 50)} · استفاده {fa(item.usage_count || 0)}</span>
        </div>
        {canEdit && <Select className="h-8" value={item.category || ""} onChange={(event) => onSpectrum(event.target.value)} options={[{ value: "", label: "بدون طیف" }, ...SPECTRA.map(([value, label]) => ({ value, label }))]} />}
        <div className="flex flex-wrap gap-2">
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
