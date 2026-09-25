import { useEffect, useState } from "react";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Page } from "../components/page";
import { Alert } from "@/components/ui/alert";
import { AsyncPage } from "@/components/ui/page-state";
import { useConfirm } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Stat } from "@/components/ui/stat";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ShamsiDateTime } from "@/components/ui/shamsi-datetime";
import { shamsiLabel } from "@/lib/jalali";
import { DiffList, TelegramPreview } from "@/lib/telegram";
import { apiDetail, en, fa } from "@/lib/utils";

const STATUS: Record<string, string> = {
  preview: "بازبینی",
  sending: "در حال ارسال",
  scheduled: "زمان‌بندی‌شده",
  published: "منتشر شد",
  rejected: "رد شد",
  failed: "ناموفق",
  skipped: "کنار گذاشته",
  recalled: "پس گرفته شد",
};

const CATEGORIES: [string, string][] = [
  ["", "بدون دسته"],
  ["news", "خبر"],
  ["announcement", "اطلاعیه"],
  ["consulting", "مشاوره"],
  ["motivational", "انگیزشی"],
  ["lesson", "آموزشی"],
  ["planning", "برنامه‌ریزی"],
  ["exam", "آزمون"],
  ["rank", "رتبه و آمار"],
  ["major_choice", "انتخاب رشته"],
  ["experience", "تجربه"],
  ["qa", "پرسش"],
  ["discount", "درآمد"],
  ["school", "دانشگاه"],
  ["resource", "معرفی"],
  ["general", "عمومی"],
  ["registration", "ثبت‌نام"],
];

const STAGES = [
  { name: "analyzer", title: "تحلیل‌گر", when: "قبل از نوشتن", detail: "فقط می‌گوید این متن چیست. خروجی‌اش JSON است: موضوع، اهمیت و اطمینان. اگر عدد تازه بسازد، کد آن را دور می‌ریزد." },
  { name: "generator", title: "نویسنده", when: "ساخت پیش‌نویس", detail: "سبک را از پوشه فاین‌تیون می‌گیرد: خبر کوتاه، اطلاعیه، فان یا راهنما. مقالهٔ مشاوره نمی‌سازد و جملهٔ منبع را کپی نمی‌کند." },
  { name: "validator", title: "بازبین", when: "بعد از نوشتن", detail: "اگر ادعای تازه‌ای ببیند فقط REVIEW می‌گوید. عدد و نقل‌قول را کد، جدا از این متن، هم رد می‌کند." },
  { name: "regenerator_fresh", title: "شروع تازه", when: "اگر شروع تکراری شد", detail: "همان واقعیت را با شروع و ریتم دیگر می‌نویسد تا پست‌ها شبیه هم نشوند." },
  { name: "regenerator_shorter", title: "کوتاه‌تر", when: "دکمهٔ کوتاه‌تر", detail: "همان واقعیت را کوتاه می‌کند و عدد و اسم منبع را نگه می‌دارد." },
  { name: "regenerator_rewrite", title: "چینش تازه", when: "دکمهٔ چینش تازه", detail: "جمله‌ها را جابه‌جا می‌کند. واقعیت تازه نمی‌سازد." },
];

const RELEASABLE = new Set(["preview", "scheduled", "failed", "recalled", "rejected"]);

function pendingLabel(key: string) {
  const action = key.split(":").pop();
  return {
    publish: "در حال انتشار در کانال",
    unsend: "در حال پس گرفتن از کانال",
    reject: "در حال انتقال به بایگانی",
    approve: "در حال زمان‌بندی",
    test: "در حال ارسال آزمایشی",
    restore: "در حال برگرداندن به صف",
    preview: "در حال ساخت خروجی",
    save: "در حال ذخیره متن",
    fresh: "در حال ساخت شروع تازه",
    shorter: "در حال کوتاه کردن",
    rewrite: "در حال چینش تازه",
  }[action || ""] || "در حال انجام";
}

function categoryLabel(value: string | null | undefined) {
  return CATEGORIES.find(([key]) => key === (value || ""))?.[1] || value || "عمومی";
}

function whenLabel(value: string | null | undefined) {
  if (!value) return "هنوز نیست";
  const label = shamsiLabel(value);
  return label === "ثبت نشده" ? "زمان نامعتبر" : label;
}

function reasonLabel(value: string | null | undefined) {
  if (!value) return "";
  return {
    needs_review: "نیاز به بازبینی",
    similar: "شبیه پست اخیر",
    skip: "مدل این خبر را رد کرد",
  }[value] || value;
}

export default function Automation() {
  const [data, setData] = useState<any>(null);
  const [channels, setChannels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [msg, setMsg] = useState("");
  const [source, setSource] = useState("");
  const [sourceCategory, setSourceCategory] = useState("");
  const [hour, setHour] = useState("9");
  const [minute, setMinute] = useState("0");
  const [slotCategory, setSlotCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState<any>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [bucket, setBucket] = useState<"queue" | "archive">("queue");
  const [pending, setPending] = useState("");
  const [preview, setPreview] = useState<any>(null);
  const [proposal, setProposal] = useState<any>(null);
  const [tagForm, setTagForm] = useState({ tag: "", category: "general", priority: "60" });
  const [extraForm, setExtraForm] = useState({ name: "", body: "" });
  const [promptDrafts, setPromptDrafts] = useState<Record<string, string>>({});
  const [styleFolder, setStyleFolder] = useState("flash");
  const role = useAuth((state) => state.role);
  const canEdit = !role || role !== "VIEWER";
  const canPublish = !role || role === "OWNER" || role === "ADMIN";

  const { ask, dialog } = useConfirm();

  async function load(status = statusFilter, category = categoryFilter) {
    setLoading(true);
    setLoadError("");
    try {
      const state = await api.get("/api/automation", {
        params: { draft_status: status || undefined, draft_category: category || undefined },
        timeout: 12000,
      });
      setData(state.data);
      setLoadError("");
      setPromptDrafts((prev) => {
        const next = { ...prev };
        for (const item of state.data.prompts || []) {
          if (next[item.name] === undefined) next[item.name] = item.body || "";
        }
        return next;
      });
    } catch (error: any) {
      const detail = error.response?.data?.detail;
      setLoadError(error.code === "ECONNABORTED" ? "خواندن صف طول کشید. دوباره بزن." : (typeof detail === "string" ? detail : "صف اتوماسیون خوانده نشد"));
    } finally {
      setLoading(false);
    }
    api.get("/api/channels", { timeout: 12000 }).then((listed) => setChannels(listed.data || [])).catch(() => {});
  }
  useEffect(() => { load().catch(() => setLoadError("صف اتوماسیون خوانده نشد")); }, [statusFilter, categoryFilter]);

  async function saveConfig(patch: Record<string, unknown>) {
    try {
      await api.patch("/api/automation", patch);
      await load();
    } catch (error: any) {
      setMsg(apiDetail(error, "ذخیره نشد"));
    }
  }

  async function run(action: () => Promise<void>, fallback: string) {
    try {
      await action();
    } catch (error: any) {
      setMsg(apiDetail(error, fallback));
    }
  }

  async function act(key: string, action: () => Promise<void>, fallback: string) {
    if (pending) return;
    setPending(key);
    setMsg("");
    try {
      await action();
    } catch (error: any) {
      setMsg(apiDetail(error, fallback));
    } finally {
      setPending(null);
    }
  }

  if (!data) {
    return (
      <AsyncPage
        kicker="اتوماسیون"
        title="پست خودکار"
        description="منبع خوانده می‌شود، در پوشهٔ سبک طبقه می‌شود، و پست با لحن کانال‌های کنکور ساخته می‌شود."
        loading={loading && !loadError}
        error={loadError}
        onRetry={() => load()}
        skeleton="stats"
      />
    );
  }

  const metrics = data.metrics || {};
  const hashtags = data.hashtags || [];
  const grouped = CATEGORIES.filter(([value]) => value).map(([value, label]) => ({
    value,
    label,
    items: hashtags.filter((tag: any) => (tag.category || "general") === value),
  })).filter((group) => group.items.length);
  const extras = (data.prompts || []).filter((item: any) => item.kind === "extra");
  const stages = STAGES.map((stage) => ({ ...stage, saved: (data.prompts || []).find((item: any) => item.name === stage.name) }));

  return (
    <Page
      kicker="اتوماسیون"
      title="پست خودکار"
      description="آخرین پست کانال خوانده می‌شود. تبلیغ کنار می‌رود. خبر کوتاه خلاصه نمی‌شود. اگر عکس داشته باشد، همان عکس به‌صورت تصویر، نه فایل، با کپشن می‌رود."
      actions={<Button variant="brand" disabled={!canEdit} loading={busy} onClick={async () => {
        setBusy(true);
        try {
          const { data: result } = await api.post("/api/automation/collect");
          const filed = Number(result.filed || 0);
          const photos = Number(result.photos || 0);
          const ads = Number(result.ads || 0);
          setMsg(result.error || (result.skipped === "disabled" ? "اتوماسیون خاموش است" : result.skipped === "paused" ? "صف متوقف است" : `پیش‌نویس تازه: ${fa(result.created ?? 0)}${photos ? ` · عکس: ${fa(photos)}` : ""}${ads ? ` · تبلیغ رد شد: ${fa(ads)}` : ""}${filed ? ` · پوشه فاین‌تیون: ${fa(filed)}` : ""}${result.recent ? " · پست‌های اخیر کانال خوانده شد" : ""}`));
          await load();
        } catch (error: any) { setMsg(apiDetail(error, "جمع‌آوری انجام نشد")); }
        finally { setBusy(false); }
      }}>جمع‌آوری الان</Button>}
    >
      <Alert title="مسیر یک پست">
        هر جمع‌آوری پست را در پوشهٔ فاین‌تیون طبقه می‌کند. نویسنده از همان پوشه می‌فهمد خبر را کوتاه بگوید، فان را نصیحت نکند و اطلاعیه را مقاله نکند. لینک خصوصی فقط وقتی ثبت می‌شود که اکانت خبر از قبل عضو همان کانال باشد؛ جوین خودکار انجام نمی‌شود.
      </Alert>
      {data.last_error && <Alert variant="destructive" title={data.last_error} />}
      {dialog}
      {loadError && <Alert variant="warning" title={loadError}><Button variant="outline" onClick={() => load()}>دوباره</Button></Alert>}
      {msg && <Alert>{msg}</Alert>}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat size="sm" label="منتظر بازبینی" value={fa(metrics.preview ?? 0)} />
        <Stat size="sm" label="زمان‌بندی‌شده" value={fa(metrics.scheduled ?? 0)} />
        <Stat size="sm" label="منتشرشدهٔ امروز" value={fa(metrics.published_today ?? 0)} unit={`از ${fa(metrics.daily_cap ?? data.daily_cap ?? 6)}`} />
        <Stat size="sm" label="ناموفق" value={fa(metrics.failed ?? 0)} />
      </div>

      <Tabs defaultValue="publish" variant="underline">
        <TabsList className="flex-wrap" aria-label="بخش‌های پست خودکار">
          <TabsTrigger value="publish">انتشار</TabsTrigger>
          <TabsTrigger value="sources">منابع</TabsTrigger>
          <TabsTrigger value="slots">زمان‌بندی</TabsTrigger>
          <TabsTrigger value="tags">هشتگ</TabsTrigger>
          <TabsTrigger value="drafts">پیش‌نویس</TabsTrigger>
          <TabsTrigger value="finetune">فاین‌تیون</TabsTrigger>
          <TabsTrigger value="prompts">پرامپت</TabsTrigger>
          <TabsTrigger value="logs">گزارش</TabsTrigger>
        </TabsList>

        <TabsContent value="publish">
          <Card>
            <CardHeader><CardTitle>کلیدهای صف</CardTitle></CardHeader>
            <CardContent className="grid gap-3 lg:grid-cols-2">
              <ToggleRow disabled={!canEdit} checked={!!data.enabled} label="جمع‌آوری خودکار" hint="در فاصلهٔ تعیین‌شده منبع‌های روشن خوانده می‌شوند." onChange={(value) => saveConfig({ enabled: value })} />
              <ToggleRow disabled={!canEdit || !canPublish} checked={!!data.auto_publish} label="انتشار بدون تأیید دستی" hint="فقط مالک و ادمین. پستِ تأییدشده در ساعت مشخص می‌رود." onChange={(value) => saveConfig({ auto_publish: value })} />
              <ToggleRow disabled={!canEdit} checked={!!data.paused} label="توقف اضطراری صف" hint="جمع‌آوری و انتشار خودکار هر دو می‌ایستند." onChange={(value) => saveConfig({ paused: value })} />
              <ToggleRow disabled={!canEdit} checked={data.balance_categories !== false} label="تعادل دسته در سقف روزانه" hint="یک دسته تمام سهم روز را نمی‌گیرد." onChange={(value) => saveConfig({ balance_categories: value })} />
              <Field label="سقف انتشار روزانه">
                <Input type="number" min={1} max={48} defaultValue={data.daily_cap || 6} disabled={!canEdit} onBlur={(event) => {
                  const parsed = Number(en(event.target.value));
                  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 48) {
                    setMsg("سقف روزانه باید بین ۱ و ۴۸ باشد");
                    event.target.value = String(data.daily_cap || 6);
                    return;
                  }
                  if (parsed !== Number(data.daily_cap || 6)) saveConfig({ daily_cap: parsed });
                }} />
              </Field>
              <Field label="فاصلهٔ جمع‌آوری، دقیقه">
                <Input type="number" min={5} max={240} defaultValue={data.collect_interval_minutes || 20} disabled={!canEdit} onBlur={(event) => {
                  const parsed = Number(en(event.target.value));
                  if (!Number.isInteger(parsed) || parsed < 5 || parsed > 240) {
                    setMsg("فاصله جمع‌آوری باید بین ۵ و ۲۴۰ دقیقه باشد");
                    event.target.value = String(data.collect_interval_minutes || 20);
                    return;
                  }
                  if (parsed !== Number(data.collect_interval_minutes || 20)) saveConfig({ collect_interval_minutes: parsed });
                }} />
              </Field>
              <Field label="ذکر منبع">
                <Select
                  value={data.attribution_mode || "news"}
                  disabled={!canEdit}
                  onChange={(event) => saveConfig({ attribution_mode: event.target.value })}
                  options={[
                    { value: "news", label: "فقط خبر و اطلاعیه" },
                    { value: "always", label: "همیشه" },
                    { value: "never", label: "هرگز" },
                  ]}
                />
              </Field>
              <Field label="کانال مقصد">
                <Select
                  value={String(data.target_chat_id || "")}
                  disabled={!canEdit}
                  onChange={(event) => saveConfig({ target_chat_id: event.target.value ? Number(event.target.value) : null })}
                  options={[{ value: "", label: "انتخاب نشده" }, ...(Array.isArray(channels) ? channels : []).map((channel) => ({ value: String(channel.chat_id), label: channel.title || channel.username || String(channel.chat_id) }))]}
                />
              </Field>
              <p className="text-xs text-muted-foreground lg:col-span-2">ساعت بعدی، تهران: {whenLabel(data.next_slot)} · آخرین جمع‌آوری، تهران: {whenLabel(data.last_collect_at)}</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sources">
          <Card>
            <CardHeader><CardTitle>کانال‌های منبع</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 md:grid-cols-[1fr_180px_auto]">
                <Input dir="ltr" value={source} onChange={(event) => setSource(event.target.value)} placeholder="@channel یا https://t.me/+invite" />
                <Select value={sourceCategory} onChange={(event) => setSourceCategory(event.target.value)} options={CATEGORIES.map(([value, label]) => ({ value, label }))} />
                <Button variant="outline" disabled={!canEdit || !source.trim()} onClick={() => run(async () => {
                  await api.post("/api/automation/sources", { username: source, category_hint: sourceCategory || null });
                  setSource("");
                  setMsg("منبع ثبت شد");
                  await load();
                }, "منبع ثبت نشد")}>افزودن منبع</Button>
              </div>
              <p className="text-xs text-muted-foreground">لینک خصوصی مثل t.me/+... فقط اگر اکانت خبر از قبل عضو همان کانال باشد ذخیره می‌شود. پنل خودش جوین نمی‌کند.</p>
              {data.sources?.length ? (
                <Table>
                  <TableHeader><TableRow><TableHead>منبع</TableHead><TableHead>اولویت و فاصله</TableHead><TableHead>وضعیت</TableHead><TableHead /></TableRow></TableHeader>
                  <TableBody>
                    {data.sources.map((item: any) => (
                      <TableRow key={item.id}>
                        <TableCell>
                          {item.title ? (
                            <>
                              <div>{item.title}</div>
                              <div dir="ltr" className="text-xs text-muted-foreground">{item.username}</div>
                            </>
                          ) : (
                            <div dir="ltr">{item.username}</div>
                          )}
                          <div className="text-xs text-muted-foreground">{categoryLabel(item.category_hint)}</div>
                        </TableCell>
                        <TableCell>
                          <Select className="h-8 text-xs" value={item.priority || "normal"} disabled={!canEdit} onChange={(event) => run(async () => { await api.patch(`/api/automation/sources/${item.id}`, { priority: event.target.value }); await load(); }, "اولویت ذخیره نشد")} options={[{ value: "high", label: "بالا" }, { value: "normal", label: "معمولی" }, { value: "low", label: "پایین" }]} />
                          <Input className="mt-1 h-8" type="number" min={5} defaultValue={item.interval_minutes || 20} disabled={!canEdit} onBlur={(event) => run(async () => { await api.patch(`/api/automation/sources/${item.id}`, { interval_minutes: Number(event.target.value) || 20 }); }, "فاصله ذخیره نشد")} />
                        </TableCell>
                        <TableCell className="text-xs">{item.last_error || `تا پیام ${fa(item.last_message_id || 0)}`}</TableCell>
                        <TableCell>
                          <div className="flex flex-wrap items-center gap-2">
                            <Switch checked={item.enabled !== false} disabled={!canEdit} onCheckedChange={(value) => run(async () => { await api.patch(`/api/automation/sources/${item.id}`, { enabled: value }); await load(); }, "وضعیت ذخیره نشد")} />
                            <Button size="sm" variant="outline" disabled={!canEdit} onClick={() => run(async () => { const { data: probe } = await api.post(`/api/automation/sources/${item.id}/probe`); setMsg(probe.readable ? "منبع باز شد" : probe.last_error); await load(); }, "آزمایش نشد")}>آزمایش</Button>
                            <Button size="sm" variant="destructive" disabled={!canEdit} onClick={() => run(async () => { await api.delete(`/api/automation/sources/${item.id}`); await load(); }, "حذف نشد")}>حذف</Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : <EmptyState title="منبعی نیست" description="یک کانال عمومی خبری یا مشاوره‌ای اضافه کن." />}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="slots">
          <Card>
            <CardHeader><CardTitle>ساعت انتشار، به وقت تهران</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-[90px_90px_180px_auto]">
                <Field label="ساعت"><Input type="number" min={0} max={23} value={hour} onChange={(event) => setHour(event.target.value)} /></Field>
                <Field label="دقیقه"><Input type="number" min={0} max={59} value={minute} onChange={(event) => setMinute(event.target.value)} /></Field>
                <Field label="دسته"><Select value={slotCategory} onChange={(event) => setSlotCategory(event.target.value)} options={CATEGORIES.map(([value, label]) => ({ value, label }))} /></Field>
                <div className="flex items-end"><Button variant="outline" disabled={!canEdit} onClick={() => run(async () => { await api.post("/api/automation/slots", { hour: Number(hour), minute: Number(minute), category: slotCategory || null }); setMsg("ساعت ثبت شد"); await load(); }, "ساعت ثبت نشد")}>ساعت تازه</Button></div>
              </div>
              {data.slots?.length ? (
                <div className="grid gap-2 md:grid-cols-2">
                  {data.slots.map((slot: any) => (
                    <div key={slot.id} className="flex items-center justify-between rounded-xl border border-border px-4 py-3 text-sm">
                      <div>
                        <b>{fa(String(slot.hour).padStart(2, "0"))}:{fa(String(slot.minute).padStart(2, "0"))}</b>
                        <p className="text-xs text-muted-foreground">{slot.category ? categoryLabel(slot.category) : "هر دسته"} · هر روز، ساعت تهران</p>
                      </div>
                      <span className="flex items-center gap-2">
                        <Switch checked={slot.enabled !== false} disabled={!canEdit} onCheckedChange={(value) => run(async () => { await api.patch(`/api/automation/slots/${slot.id}`, { enabled: value }); await load(); }, "ساعت ذخیره نشد")} />
                        <Button size="sm" variant="destructive" disabled={!canEdit} onClick={() => run(async () => { await api.delete(`/api/automation/slots/${slot.id}`); await load(); }, "حذف نشد")}>حذف</Button>
                      </span>
                    </div>
                  ))}
                </div>
              ) : <EmptyState title="ساعتی نیست" description="مثلاً ۹ صبح برای خبر و ۶ عصر برای مشاوره." />}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tags">
          <Card>
            <CardHeader><CardTitle>هشتگ‌ها</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">حداکثر سه هشتگ به پست می‌چسبد. اول هشتگِ همان دسته با اولویت بالاتر، بعد هشتگی که واژه‌اش در متن منبع باشد. ممنوع‌ها هرگز اضافه نمی‌شوند.</p>
              <div className="grid gap-2 md:grid-cols-[1fr_180px_110px_auto]">
                <Field label="هشتگ تازه"><Input value={tagForm.tag} disabled={!canEdit} onChange={(event) => setTagForm({ ...tagForm, tag: event.target.value })} placeholder="بورسیه یا انتخاب رشته" /></Field>
                <Field label="دسته"><Select value={tagForm.category} disabled={!canEdit} onChange={(event) => setTagForm({ ...tagForm, category: event.target.value })} options={CATEGORIES.filter(([value]) => value).map(([value, label]) => ({ value, label }))} /></Field>
                <Field label="اولویت"><Input type="number" min={1} max={200} value={tagForm.priority} disabled={!canEdit} onChange={(event) => setTagForm({ ...tagForm, priority: event.target.value })} /></Field>
                <div className="flex items-end"><Button variant="brand" disabled={!canEdit || !tagForm.tag.trim()} onClick={() => run(async () => {
                  await api.post("/api/automation/hashtags", { tag: tagForm.tag, category: tagForm.category, priority: Number(tagForm.priority) || 60 });
                  setTagForm({ tag: "", category: tagForm.category, priority: "60" });
                  setMsg("هشتگ اضافه شد");
                  await load();
                }, "هشتگ اضافه نشد")}>افزودن</Button></div>
              </div>
              {grouped.length ? grouped.map((group) => (
                <section key={group.value} className="space-y-2">
                  <h3 className="text-sm font-semibold">{group.label}</h3>
                  <div className="grid gap-2">
                    {group.items.map((tag: any) => (
                      <div key={tag.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border px-3 py-2">
                        <div className="min-w-0">
                          <b dir="ltr">#{tag.tag}</b>
                          <p className="text-xs text-muted-foreground">{tag.forbidden ? "ممنوع" : tag.enabled ? "فعال" : "خاموش"} · اولویت {fa(tag.priority || 0)}</p>
                        </div>
                        <div className="flex flex-wrap items-center gap-3">
                          <Select className="h-8 w-36 text-xs" value={tag.category || "general"} disabled={!canEdit} onChange={(event) => run(async () => { await api.patch(`/api/automation/hashtags/${tag.id}`, { category: event.target.value }); await load(); }, "دسته ذخیره نشد")} options={CATEGORIES.filter(([value]) => value).map(([value, label]) => ({ value, label }))} />
                          <Input className="h-8 w-20" type="number" min={1} max={200} defaultValue={tag.priority || 60} disabled={!canEdit} aria-label="اولویت" onBlur={(event) => { const next = Number(event.target.value) || 60; if (next !== tag.priority) run(async () => { await api.patch(`/api/automation/hashtags/${tag.id}`, { priority: next }); await load(); }, "اولویت ذخیره نشد"); }} />
                          <label className="flex items-center gap-2 text-xs">فعال <Switch checked={!!tag.enabled && !tag.forbidden} disabled={!canEdit} onCheckedChange={(value) => run(async () => { await api.patch(`/api/automation/hashtags/${tag.id}`, { enabled: value, forbidden: value ? false : tag.forbidden }); await load(); }, "هشتگ ذخیره نشد")} /></label>
                          <label className="flex items-center gap-2 text-xs">ممنوع <Switch checked={!!tag.forbidden} disabled={!canEdit} onCheckedChange={(value) => run(async () => { await api.patch(`/api/automation/hashtags/${tag.id}`, { forbidden: value }); await load(); }, "هشتگ ذخیره نشد")} /></label>
                          <Button size="sm" variant="destructive" disabled={!canEdit} onClick={() => ask(`#${tag.tag} حذف شود؟`, () => run(async () => { await api.delete(`/api/automation/hashtags/${tag.id}`); await load(); }, "حذف نشد"))}>حذف</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )) : <EmptyState title="هشتگی نیست" description="اولین هشتگ را بالا اضافه کن." />}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="drafts">
          <Card>
            <CardHeader><CardTitle>{bucket === "archive" ? "بایگانی" : "پیش‌نویس‌ها"}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant={bucket === "queue" ? "brand" : "outline"} onClick={() => setBucket("queue")}>صف پیش‌نویس</Button>
                <Button size="sm" variant={bucket === "archive" ? "brand" : "outline"} onClick={() => setBucket("archive")}>بایگانی{metrics.archive ? ` · ${fa(metrics.archive)}` : ""}</Button>
              </div>
              {bucket === "archive" && <p className="text-xs text-muted-foreground">ردشده‌ها اینجاست. از همین‌جا می‌شود دوباره منتشرشان کرد.</p>}
              <div className="grid gap-2 sm:grid-cols-2">
                {bucket === "queue" && <Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} options={[{ value: "", label: "همه وضعیت‌ها" }, ...Object.entries(STATUS).filter(([value]) => value !== "rejected").map(([value, label]) => ({ value, label }))]} />}
                <Select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} options={CATEGORIES.map(([value, label]) => ({ value, label: value ? label : "همه دسته‌ها" }))} />
              </div>
              {(bucket === "archive" ? data.archive : data.drafts)?.length ? (
                <div className="space-y-4">
                  {(bucket === "archive" ? data.archive : data.drafts).map((draft: any) => (
                    <article key={draft.id} aria-busy={pending.startsWith(`${draft.id}:`) || undefined} className={`space-y-3 rounded-2xl border p-4 transition-colors ${pending.startsWith(`${draft.id}:`) ? "border-brand/70 bg-brand/5" : "border-border"}`}>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={draft.status === "failed" ? "destructive" : draft.status === "published" ? "success" : "secondary"}>{STATUS[draft.status] || draft.status}</Badge>
                        <span className="text-xs text-muted-foreground">{draft.source_label} · {draft.style_label || categoryLabel(draft.category)} · {draft.confidence || "—"} {draft.has_photo ? "· همراه عکس" : draft.has_media ? "· کپشن" : ""} {draft.rewrite === "preserve" ? "· بدون خلاصه" : draft.rewrite === "summarize" ? "· خلاصه" : ""}</span>
                        {draft.hashtags && <span className="text-xs text-muted-foreground" dir="ltr">{draft.hashtags}</span>}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        دریافت از کانال: {whenLabel(draft.source_at || draft.created_at)}
                        {!draft.source_at ? " · زمان دقیق منبع ذخیره نشده، این زمان ثبت در پنل است" : ""}
                        {draft.scheduled_at ? ` · انتشار برنامه‌شده: ${whenLabel(draft.scheduled_at)}` : ""}
                        {draft.published_at ? ` · منتشر شد: ${whenLabel(draft.published_at)}` : ""}
                      </p>
                      {(draft.has_photo || draft.image_note) && <DraftPhoto id={draft.id} />}
                      {pending.startsWith(`${draft.id}:`) && <p className="text-xs text-brand" aria-live="polite">{pendingLabel(pending)}…</p>}
                      {edit?.id === draft.id ? (
                        <Textarea value={edit.body} onChange={(event) => setEdit({ ...edit, body: event.target.value })} />
                      ) : draft.body ? <p className="whitespace-pre-wrap text-sm">{draft.body}</p> : <p className="text-sm text-muted-foreground">برای این منبع هنوز متنی ساخته نشده. منبع پایین جدا از پیش‌نویس است.</p>}
                      {draft.source_content && (
                        <details className="text-xs text-muted-foreground">
                          <summary>متن منبع، جدا از پیش‌نویس</summary>
                          <p className="mt-2 whitespace-pre-wrap">{draft.source_content}</p>
                        </details>
                      )}
                      {draft.image_note && <p className="text-xs text-muted-foreground">از روی عکس: {draft.image_note}</p>}
                      {(draft.writer_model || draft.vision_model) && <p className="text-xs text-muted-foreground">مدل نویسنده: {draft.writer_model || "—"}{draft.vision_model ? ` · مدل عکس: ${draft.vision_model}` : ""}</p>}
                      {draft.analysis_summary && <p className="text-xs text-muted-foreground">تحلیل: {draft.analysis_summary}</p>}
                      {draft.versions?.length ? (
                        <details className="text-xs text-muted-foreground">
                          <summary>نسخه‌های قبلی</summary>
                          {draft.versions.map((item: any) => (
                            <div key={`${item.version}-${item.reason}`} className="mt-2 space-y-1">
                              <p>نسخه {fa(item.version)} · {item.reason}</p>
                              <p className="whitespace-pre-wrap">{item.body}</p>
                              {canEdit && <Button size="sm" variant="outline" onClick={() => run(async () => { await api.post(`/api/automation/drafts/${draft.id}/restore-version?version=${item.version}`); setMsg("نسخه برگردانده شد"); await load(); }, "برگردانده نشد")}>برگرداندن این نسخه</Button>}
                            </div>
                          ))}
                        </details>
                      ) : null}
                      {draft.error && <p className="text-xs text-destructive">{reasonLabel(draft.error)}</p>}
                      <div className="grid gap-2 lg:grid-cols-3">
                        <Select value={draft.category} disabled={!canEdit} onChange={(event) => run(async () => { await api.patch(`/api/automation/drafts/${draft.id}`, { category: event.target.value }); await load(); }, "دسته ذخیره نشد")} options={CATEGORIES.filter(([value]) => value).map(([value, label]) => ({ value, label }))} />
                        <Input className="h-10" defaultValue={draft.hashtags || ""} disabled={!canEdit} placeholder="#خبر" onBlur={(event) => { if (event.target.value !== (draft.hashtags || "")) run(async () => { await api.patch(`/api/automation/drafts/${draft.id}`, { hashtags: event.target.value }); }, "هشتگ ذخیره نشد"); }} />
                        <p className="self-center text-xs text-muted-foreground">زمان‌بندی با تقویم شمسی، ساعت تهران</p>
                      </div>
                      <ShamsiDateTime key={draft.id} value={draft.scheduled_at} disabled={!canEdit} onChange={(iso) => run(async () => { await api.patch(`/api/automation/drafts/${draft.id}`, { scheduled_at: iso }); setMsg("زمان تهران ذخیره شد"); await load(); }, "زمان ذخیره نشد")} />
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" variant="outline" disabled={!canEdit || !!pending} onClick={() => setEdit(edit?.id === draft.id ? null : { ...draft })}>{edit?.id === draft.id ? "بستن" : "ویرایش"}</Button>
                        {edit?.id === draft.id && <Button size="sm" variant="brand" loading={pending === `${draft.id}:save`} disabled={!!pending} onClick={() => act(`${draft.id}:save`, async () => { await api.patch(`/api/automation/drafts/${draft.id}`, { body: edit.body }); setEdit(null); setMsg("متن ذخیره شد"); await load(); }, "متن ذخیره نشد")}>ذخیره متن</Button>}
                        {draft.body && <Button size="sm" variant="outline" loading={pending === `${draft.id}:preview`} disabled={!!pending} onClick={() => act(`${draft.id}:preview`, async () => { setPreview({ draftId: draft.id, has_photo: draft.has_photo, ...(await api.get(`/api/automation/drafts/${draft.id}/preview`)).data }); }, "پیش‌نمایش نشد")}>خروجی ارسال</Button>}
                        {canPublish && draft.body && RELEASABLE.has(draft.status) && <Button size="sm" variant="outline" loading={pending === `${draft.id}:test`} disabled={!!pending} onClick={() => act(`${draft.id}:test`, async () => { await api.post(`/api/automation/drafts/${draft.id}/test-send`); setMsg("پیش‌نمایش به خودت رفت، نه کانال"); }, "ارسال آزمایشی نشد")}>بفرست به خودم</Button>}
                        {canPublish && draft.body && RELEASABLE.has(draft.status) && <Button size="sm" variant="outline" loading={pending === `${draft.id}:approve`} disabled={!!pending} onClick={() => act(`${draft.id}:approve`, async () => { await api.post(`/api/automation/drafts/${draft.id}/approve`); setMsg("برای ساعت بعدی زمان‌بندی شد"); setBucket("queue"); await load(); }, "تأیید نشد")}>تأیید</Button>}
                        {canPublish && draft.body && RELEASABLE.has(draft.status) && <Button size="sm" variant="brand" loading={pending === `${draft.id}:publish`} disabled={!!pending} onClick={() => act(`${draft.id}:publish`, async () => { await api.post(`/api/automation/drafts/${draft.id}/publish`); setMsg("در کانال منتشر شد"); setBucket("queue"); await load(); }, "منتشر نشد")}>انتشار الان</Button>}
                        {canPublish && draft.published_url && draft.message_id && <a className="self-center text-xs underline" href={draft.published_url} target="_blank" rel="noreferrer">پیام کانال</a>}
                        {canPublish && draft.message_id && draft.status === "published" && <Button size="sm" variant="destructive" loading={pending === `${draft.id}:unsend`} disabled={!!pending} onClick={() => act(`${draft.id}:unsend`, async () => { await api.post(`/api/automation/drafts/${draft.id}/unsend`); setMsg("از کانال حذف شد. می‌توانی دوباره منتشرش کنی."); await load(); }, "حذف نشد")}>پس بگیر</Button>}
                        {canEdit && <Button size="sm" variant="outline" loading={pending === `${draft.id}:fresh`} disabled={!!pending} onClick={() => act(`${draft.id}:fresh`, async () => { setProposal({ id: draft.id, mode: "fresh", ...(await api.post(`/api/automation/drafts/${draft.id}/regenerate?mode=fresh`)).data }); }, "بازنویسی نشد")}>شروع تازه</Button>}
                        {canEdit && <Button size="sm" variant="outline" loading={pending === `${draft.id}:shorter`} disabled={!!pending} onClick={() => act(`${draft.id}:shorter`, async () => { setProposal({ id: draft.id, mode: "shorter", ...(await api.post(`/api/automation/drafts/${draft.id}/regenerate?mode=shorter`)).data }); }, "کوتاه نشد")}>کوتاه‌تر</Button>}
                        {canEdit && <Button size="sm" variant="outline" loading={pending === `${draft.id}:rewrite`} disabled={!!pending} onClick={() => act(`${draft.id}:rewrite`, async () => { setProposal({ id: draft.id, mode: "rewrite", ...(await api.post(`/api/automation/drafts/${draft.id}/regenerate?mode=rewrite`)).data }); }, "چینش عوض نشد")}>چینش تازه</Button>}
                        {(draft.status === "skipped" || draft.status === "rejected") && canEdit && <Button size="sm" variant="outline" loading={pending === `${draft.id}:restore`} disabled={!!pending} onClick={() => act(`${draft.id}:restore`, async () => { await api.post(`/api/automation/drafts/${draft.id}/restore`); setBucket("queue"); setMsg("به صف پیش‌نویس برگشت"); await load(); }, "برگردانده نشد")}>برگردان به پیش‌نویس</Button>}
                        {canEdit && draft.status !== "rejected" && draft.status !== "published" && draft.status !== "sending" && <Button size="sm" variant="destructive" loading={pending === `${draft.id}:reject`} disabled={!!pending} onClick={() => act(`${draft.id}:reject`, async () => { await api.post(`/api/automation/drafts/${draft.id}/reject`); setBucket("archive"); setMsg("به بایگانی رفت. از همان‌جا می‌شود منتشرش کرد."); await load(); }, "رد نشد")}>رد</Button>}
                      </div>
                    </article>
                  ))}
                </div>
              ) : <EmptyState title={bucket === "archive" ? "بایگانی خالی است" : "پیش‌نویسی نیست"} description={bucket === "archive" ? "ردشده‌ها اینجا می‌مانند و از همین‌جا می‌شود منتشرشان کرد." : "بعد از جمع‌آوری، متن ساخته‌شده اینجا دیده می‌شود. تا تأیید یا رسیدن ساعت، در کانال نمی‌رود."} />}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="prompts">
          <div className="space-y-3">
            <Alert title="این‌ها دستور هوش مصنوعی‌اند، نه متن کانال">
              شش مرحلهٔ اصلی همیشه در مسیر پست صدا زده می‌شوند. دستور اضافه فقط به نویسنده و بازنویس می‌چسبد. حتی اگر متن را عوض کنی، کد همچنان عدد، نقل‌قول و کپیِ نزدیک را رد می‌کند و قفل واقعیت را به آخر دستور نویسنده می‌چسباند.
            </Alert>
            {stages.map((stage) => (
              <Card key={stage.name}>
                <CardHeader>
                  <CardTitle>{stage.title}</CardTitle>
                  <p className="text-xs text-muted-foreground">{stage.when} · نسخه {fa(stage.saved?.version || 1)} · {stage.name}</p>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">{stage.detail}</p>
                  <Textarea value={promptDrafts[stage.name] ?? stage.saved?.body ?? ""} disabled={!canEdit} onChange={(event) => setPromptDrafts({ ...promptDrafts, [stage.name]: event.target.value })} />
                  <div className="flex flex-wrap gap-2">
                    <Button variant="brand" disabled={!canEdit} onClick={() => run(async () => {
                      const body = promptDrafts[stage.name] ?? stage.saved?.body ?? "";
                      const { data: saved } = await api.post("/api/automation/prompts", { name: stage.name, body, kind: "stage" });
                      setPromptDrafts((prev) => ({ ...prev, [stage.name]: saved.body }));
                      setMsg(`${stage.title} به‌صورت نسخهٔ تازه ذخیره شد`);
                      await load();
                    }, "پرامپت ذخیره نشد")}>ذخیره نسخهٔ تازه</Button>
                    <Button variant="outline" disabled={!canEdit} onClick={() => run(async () => {
                      const { data: saved } = await api.post(`/api/automation/prompts/${stage.name}/restore`);
                      setPromptDrafts((prev) => ({ ...prev, [stage.name]: saved.body }));
                      setMsg("متن پایه برگشت؛ نسخهٔ قبلی پاک نشد");
                      await load();
                    }, "متن پایه برنگشت")}>بازگشت به متن پایه</Button>
                  </div>
                </CardContent>
              </Card>
            ))}
            <Card>
              <CardHeader><CardTitle>دستور اضافه</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">مثلاً «تیتر را کوتاه‌تر کن» یا «فان را نصیحت نکن». این متن جای پوشهٔ فاین‌تیون و بازبین واقعیت را نمی‌گیرد.</p>
                <div className="grid gap-2 md:grid-cols-[220px_1fr]">
                  <Field label="نام"><Input value={extraForm.name} disabled={!canEdit} onChange={(event) => setExtraForm({ ...extraForm, name: event.target.value })} placeholder="لحن صمیمی" /></Field>
                  <Field label="دستور"><Textarea value={extraForm.body} disabled={!canEdit} onChange={(event) => setExtraForm({ ...extraForm, body: event.target.value })} /></Field>
                </div>
                <Button variant="outline" disabled={!canEdit || extraForm.name.trim().length < 2 || extraForm.body.trim().length < 24} onClick={() => run(async () => {
                  await api.post("/api/automation/prompts", { name: extraForm.name, body: extraForm.body, kind: "extra" });
                  setExtraForm({ name: "", body: "" });
                  setMsg("دستور اضافه شد و در نوشتن بعدی استفاده می‌شود");
                  await load();
                }, "دستور اضافه نشد")}>افزودن دستور</Button>
                {extras.length ? extras.map((item: any) => (
                  <div key={item.id} className="rounded-xl border border-border p-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <b>{item.label}</b>
                      <Button size="sm" variant="destructive" disabled={!canEdit} onClick={() => run(async () => { await api.delete(`/api/automation/prompts/${item.id}`); await load(); }, "حذف نشد")}>حذف</Button>
                    </div>
                    <p className="whitespace-pre-wrap text-sm text-muted-foreground">{item.body}</p>
                  </div>
                )) : <p className="text-xs text-muted-foreground">دستور اضافه‌ای نیست.</p>}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="finetune">
          <div className="space-y-3">
            <Card>
              <CardHeader><CardTitle>پوشهٔ سبک کانال‌های کنکور</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">هر جمع‌آوری، پست را در پوشهٔ سبک می‌گذارد و ریتم همان پوشه را اندازه می‌گیرد: طول، تعداد خط و این‌که سؤال دارد یا نه. نویسنده دفعهٔ بعد همین کارت را می‌خواند، نه جملهٔ نمونه را. وزن مدل عوض نمی‌شود. نمونهٔ غلط را حذف کن یا به پوشهٔ درست ببر تا کارت بعدی تمیزتر شود.</p>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {(data.finetune?.folders || []).map((folder: any) => (
                    <button key={folder.id} type="button" onClick={() => setStyleFolder(folder.id)} className={`cursor-pointer rounded-xl border bg-transparent p-3 text-start text-inherit ${styleFolder === folder.id ? "border-foreground" : "border-border"}`}>
                      <Stat size="sm" label={folder.label} value={fa(folder.count || 0)} />
                      <p className="mt-2 text-xs text-muted-foreground">{folder.count ? `${fa(folder.chars || 0)} حرف · ${fa(folder.lines || 0)} خط` : "هنوز خالی"}</p>
                    </button>
                  ))}
                </div>
                {(() => {
                  const folder = (data.finetune?.folders || []).find((item: any) => item.id === styleFolder) || (data.finetune?.folders || [])[0];
                  if (!folder) return null;
                  return (
                    <div className="space-y-3 rounded-xl border border-border p-3">
                      <div>
                        <p className="text-sm font-semibold">{folder.label}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{folder.angle}</p>
                      </div>
                      <p className="text-sm">{folder.rule}</p>
                      <p className="whitespace-pre-wrap text-xs leading-6 text-muted-foreground">{folder.skeleton}</p>
                      {folder.count ? <p className="text-xs text-muted-foreground">ریتم اندازه‌گرفته: حدود {fa(folder.chars || 0)} حرف و {fa(folder.lines || 0)} خط. سؤال در {fa(folder.questions || 0)} نمونه.</p> : <p className="text-xs text-muted-foreground">این پوشه هنوز خالی است. یک جمع‌آوری کافی است.</p>}
                    </div>
                  );
                })()}
                <p className="whitespace-pre-wrap rounded-xl border border-border p-3 text-xs leading-6 text-muted-foreground">{data.finetune?.card || "کارت سبک هنوز ساخته نشده."}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>نمونه‌های همین پوشه</CardTitle></CardHeader>
              <CardContent>
                {(() => {
                  const folder = (data.finetune?.folders || []).find((item: any) => item.id === styleFolder) || (data.finetune?.folders || [])[0];
                  const samples = folder?.samples || [];
                  if (!samples.length) return <p className="text-xs text-muted-foreground">نمونه‌ای نیست.</p>;
                  return (
                    <div className="space-y-3">
                      {samples.map((sample: any) => (
                        <div key={sample.id || sample.excerpt} className="space-y-2 rounded-xl border border-border p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                            <span>{sample.label || "منبع"} · {whenLabel(sample.created_at)} · {fa(sample.chars || 0)} حرف · {fa(sample.lines || 0)} خط</span>
                            <span className="flex flex-wrap gap-2">
                              <Select className="h-8 w-36 text-xs" value={folder.id} disabled={!canEdit} onChange={(event) => run(async () => { await api.patch(`/api/automation/finetune/samples/${sample.id}?folder=${event.target.value}`); setStyleFolder(event.target.value); setMsg("نمونه به پوشهٔ درست رفت و کارت سبک تازه شد"); await load(); }, "جابه‌جایی نشد")} options={(data.finetune?.folders || []).map((item: any) => ({ value: item.id, label: item.label }))} />
                              <Button size="sm" variant="destructive" disabled={!canEdit} onClick={() => ask("این نمونه از پوشه حذف شود؟", () => run(async () => { await api.delete(`/api/automation/finetune/samples/${sample.id}`); setMsg("نمونه حذف شد و کارت سبک تازه شد"); await load(); }, "حذف نشد"))}>حذف</Button>
                            </span>
                          </div>
                          <p className="whitespace-pre-wrap text-xs">{sample.excerpt}</p>
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>اصلاح‌هایی که نویسنده یاد گرفته</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                <p className="text-sm text-muted-foreground">تأیید، ویرایش، رد و انتشار در همین حافظه می‌ماند و به نوشتن بعدی می‌رسد. مدل جدید ساخته نمی‌شود.</p>
                {(data.lessons || []).length ? (data.lessons as any[]).slice().reverse().map((item: any, index: number) => (
                  <p key={`${item.note}-${index}`} className="rounded-lg border border-border px-3 py-2 text-xs">{item.note}</p>
                )) : <p className="text-xs text-muted-foreground">هنوز اصلاحی ثبت نشده. اولین رد یا ویرایش اینجا می‌ماند.</p>}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="logs">
          <Card>
            <CardHeader><CardTitle>گزارش صف</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {(data.logs || []).length ? data.logs.map((item: any, index: number) => (
                <div key={`${item.event}-${index}`} className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg border border-border px-3 py-2">
                  <span>{item.event} {item.detail ? `· ${item.detail}` : ""}</span>
                  <span className="text-xs text-muted-foreground">{item.level} · {whenLabel(item.created_at)}</span>
                </div>
              )) : <p className="text-xs text-muted-foreground">هنوز رویدادی ثبت نشده.</p>}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={!!preview} onOpenChange={(open) => !open && setPreview(null)} title="خروجی قبل از کانال" size="lg">
        {preview && (
          <div className="space-y-3">
            {preview.has_photo && preview.draftId && <DraftPhoto id={preview.draftId} />}
            <TelegramPreview html={preview.html_text} plain={preview.text} />
          </div>
        )}
      </Dialog>
      <Dialog open={!!proposal} onOpenChange={(open) => !open && setProposal(null)} title="تفاوت قبل از جایگزینی" size="lg" footer={proposal?.proposed && <Button variant="brand" onClick={() => run(async () => { await api.patch(`/api/automation/drafts/${proposal.id}`, { body: proposal.proposed }); setProposal(null); setMsg("همان متن تأییدشده جایگزین شد"); await load(); }, "جایگزین نشد")}>جایگزین کن</Button>}>
        {proposal && <><p className="whitespace-pre-wrap text-sm">{proposal.proposed}</p><DiffList rows={proposal.diff} /></>}
      </Dialog>
    </Page>
  );
}

function DraftPhoto({ id }: { id: string }) {
  const [url, setUrl] = useState<string>("");
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let live = true;
    let objectUrl = "";
    api.get(`/api/automation/drafts/${id}/photo`, { responseType: "blob", timeout: 25000 }).then((response) => {
      if (!live) return;
      const blob = response.data as Blob;
      if (!blob || blob.size < 32 || (blob.type && !blob.type.startsWith("image/") && blob.type !== "application/octet-stream")) {
        setFailed(true);
        return;
      }
      objectUrl = URL.createObjectURL(blob.type ? blob : new Blob([blob], { type: "image/jpeg" }));
      setUrl(objectUrl);
    }).catch(() => { if (live) setFailed(true); });
    return () => {
      live = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id]);
  if (failed) return <p className="rounded-xl border border-destructive/40 px-3 py-2 text-xs text-destructive">عکس این پست باز نشد. صفحه را یک بار تازه کن؛ اگر باز نشد، فایل عکس روی سرور نمانده.</p>;
  if (!url) return <div className="flex h-48 items-center justify-center rounded-xl border border-border bg-muted text-xs text-muted-foreground" aria-label="در حال خواندن عکس">در حال آوردن عکس پست…</div>;
  return (
    <>
      <button type="button" className="block w-full cursor-pointer overflow-hidden rounded-xl border border-border bg-white/5 p-2" onClick={() => setOpen(true)} aria-label="بزرگ‌نمایی عکس">
        <img src={url} alt="عکس همین پست" className="mx-auto max-h-96 w-full rounded-lg object-contain" onError={() => setFailed(true)} />
        <span className="mt-2 block text-center text-xs text-muted-foreground">عکس پست · برای بزرگ‌نمایی بزن</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen} title="عکس پست" size="lg">
        <img src={url} alt="عکس همین پست" className="max-h-[75dvh] w-full object-contain" />
      </Dialog>
    </>
  );
}

function ToggleRow({ checked, label, hint, disabled, onChange }: { checked: boolean; label: string; hint: string; disabled?: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-4 rounded-xl border border-border px-4 py-3 text-sm">
      <span>
        <span className="block">{label}</span>
        <span className="mt-1 block text-xs text-muted-foreground">{hint}</span>
      </span>
      <Switch checked={checked} disabled={disabled} onCheckedChange={onChange} />
    </label>
  );
}
