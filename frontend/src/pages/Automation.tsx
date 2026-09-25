import { useEffect, useState } from "react";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Page } from "../components/page";
import { Alert } from "@/components/ui/alert";
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
import { DiffList, TelegramPreview } from "@/lib/telegram";
import { fa } from "@/lib/utils";

const STATUS: Record<string, string> = {
  preview: "بازبینی",
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
  { name: "generator", title: "نویسنده", when: "ساخت پیش‌نویس", detail: "از منبع یک پست مستقل می‌سازد. هشتگ، فوتر و ایموجی را خودش نمی‌نویسد؛ سیستم بعداً اضافه می‌کند." },
  { name: "validator", title: "بازبین", when: "بعد از نوشتن", detail: "اگر ادعای تازه‌ای ببیند فقط REVIEW می‌گوید. عدد و نقل‌قول را کد، جدا از این متن، هم رد می‌کند." },
  { name: "regenerator_fresh", title: "شروع تازه", when: "اگر شروع تکراری شد", detail: "همان واقعیت را با شروع و ریتم دیگر می‌نویسد تا پست‌ها شبیه هم نشوند." },
  { name: "regenerator_shorter", title: "کوتاه‌تر", when: "دکمهٔ کوتاه‌تر", detail: "همان واقعیت را کوتاه می‌کند و عدد و اسم منبع را نگه می‌دارد." },
  { name: "regenerator_rewrite", title: "چینش تازه", when: "دکمهٔ چینش تازه", detail: "جمله‌ها را جابه‌جا می‌کند. واقعیت تازه نمی‌سازد." },
];

function categoryLabel(value: string | null | undefined) {
  return CATEGORIES.find(([key]) => key === (value || ""))?.[1] || value || "عمومی";
}

function whenLabel(value: string | null | undefined) {
  if (!value) return "هنوز نیست";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("fa-IR");
}

export default function Automation() {
  const [data, setData] = useState<any>(null);
  const [channels, setChannels] = useState<any[]>([]);
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
  const [preview, setPreview] = useState<any>(null);
  const [proposal, setProposal] = useState<any>(null);
  const [tagForm, setTagForm] = useState({ tag: "", category: "general", priority: "60" });
  const [extraForm, setExtraForm] = useState({ name: "", body: "" });
  const [promptDrafts, setPromptDrafts] = useState<Record<string, string>>({});
  const role = useAuth((state) => state.role);
  const canEdit = !role || role !== "VIEWER";
  const canPublish = !role || role === "OWNER" || role === "ADMIN";

  async function load(status = statusFilter, category = categoryFilter) {
    const [state, listed] = await Promise.all([
      api.get("/api/automation", { params: { draft_status: status || undefined, draft_category: category || undefined } }),
      api.get("/api/channels"),
    ]);
    setData(state.data);
    setChannels(listed.data || []);
    setPromptDrafts((prev) => {
      const next = { ...prev };
      for (const item of state.data.prompts || []) {
        if (next[item.name] === undefined) next[item.name] = item.body || "";
      }
      return next;
    });
  }
  useEffect(() => { load().catch(() => setMsg("وضعیت اتوماسیون خوانده نشد")); }, [statusFilter, categoryFilter]);

  async function saveConfig(patch: Record<string, unknown>) {
    try {
      await api.patch("/api/automation", patch);
      await load();
    } catch (error: any) {
      setMsg(error.response?.data?.detail || "ذخیره نشد");
    }
  }

  async function run(action: () => Promise<void>, fallback: string) {
    try {
      await action();
    } catch (error: any) {
      setMsg(error.response?.data?.detail || fallback);
    }
  }

  if (!data) return <Page title="پست خودکار" description="در حال خواندن تنظیم واقعی…"><p className="text-sm text-muted-foreground">صف اتوماسیون در حال بارگذاری است.</p></Page>;

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
      description="منبع خوانده می‌شود، تکراری حذف می‌شود، پست مستقل ساخته می‌شود و تا تأیید یا رسیدن ساعت در صف می‌ماند."
      actions={<Button variant="brand" disabled={busy || !canEdit} onClick={async () => {
        setBusy(true);
        try {
          const { data: result } = await api.post("/api/automation/collect");
          setMsg(result.error || (result.skipped === "disabled" ? "اتوماسیون خاموش است" : result.skipped === "paused" ? "صف متوقف است" : `پیش‌نویس تازه: ${fa(result.created ?? 0)}`));
          await load();
        } catch (error: any) { setMsg(error.response?.data?.detail || "جمع‌آوری انجام نشد"); }
        finally { setBusy(false); }
      }}>{busy ? "در حال جمع‌آوری" : "جمع‌آوری الان"}</Button>}
    >
      <Alert title="مسیر یک پست">
        منبع عمومی خوانده می‌شود، تحلیل‌گر موضوع را جدا می‌کند، نویسنده متن مستقل می‌سازد، بازبین واقعیت را چک می‌کند و هشتگ از همین فهرست اضافه می‌شود. لینک دعوت خصوصی قبول نیست. ایموجی پرمیوم هنگام ارسال از کتابخانهٔ پنل می‌آید، نه از این پرامپت‌ها.
      </Alert>
      {data.last_error && <Alert variant="destructive" title={data.last_error} />}
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
                <Input type="number" min={1} max={48} defaultValue={data.daily_cap || 6} disabled={!canEdit} onBlur={(event) => saveConfig({ daily_cap: Number(event.target.value) || 6 })} />
              </Field>
              <Field label="فاصلهٔ جمع‌آوری، دقیقه">
                <Input type="number" min={5} max={240} defaultValue={data.collect_interval_minutes || 20} disabled={!canEdit} onBlur={(event) => saveConfig({ collect_interval_minutes: Number(event.target.value) || 20 })} />
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
                  options={[{ value: "", label: "انتخاب نشده" }, ...channels.map((channel) => ({ value: String(channel.chat_id), label: channel.title || channel.username || String(channel.chat_id) }))]}
                />
              </Field>
              <p className="text-xs text-muted-foreground lg:col-span-2">ساعت بعدی: {whenLabel(data.next_slot)} · آخرین جمع‌آوری: {whenLabel(data.last_collect_at)}</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sources">
          <Card>
            <CardHeader><CardTitle>کانال‌های منبع</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 md:grid-cols-[1fr_180px_auto]">
                <Input dir="ltr" value={source} onChange={(event) => setSource(event.target.value)} placeholder="@channel یا https://t.me/channel" />
                <Select value={sourceCategory} onChange={(event) => setSourceCategory(event.target.value)} options={CATEGORIES.map(([value, label]) => ({ value, label }))} />
                <Button variant="outline" disabled={!canEdit || !source.trim()} onClick={() => run(async () => {
                  await api.post("/api/automation/sources", { username: source, category_hint: sourceCategory || null });
                  setSource("");
                  setMsg("منبع ثبت شد");
                  await load();
                }, "منبع ثبت نشد")}>افزودن منبع</Button>
              </div>
              {data.sources?.length ? (
                <Table>
                  <TableHeader><TableRow><TableHead>منبع</TableHead><TableHead>اولویت و فاصله</TableHead><TableHead>وضعیت</TableHead><TableHead /></TableRow></TableHeader>
                  <TableBody>
                    {data.sources.map((item: any) => (
                      <TableRow key={item.id}>
                        <TableCell>
                          <div dir="ltr">{item.username}</div>
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
                        <p className="text-xs text-muted-foreground">{slot.category ? categoryLabel(slot.category) : "هر دسته"}</p>
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
                          <Button size="sm" variant="destructive" disabled={!canEdit} onClick={() => { if (!confirm(`#${tag.tag} حذف شود؟`)) return; run(async () => { await api.delete(`/api/automation/hashtags/${tag.id}`); await load(); }, "حذف نشد"); }}>حذف</Button>
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
            <CardHeader><CardTitle>پیش‌نویس‌ها</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-2">
                <Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} options={[{ value: "", label: "همه وضعیت‌ها" }, ...Object.entries(STATUS).map(([value, label]) => ({ value, label }))]} />
                <Select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} options={CATEGORIES.map(([value, label]) => ({ value, label: value ? label : "همه دسته‌ها" }))} />
              </div>
              {data.drafts?.length ? (
                <div className="space-y-4">
                  {data.drafts.map((draft: any) => (
                    <article key={draft.id} className="space-y-3 rounded-2xl border border-border p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={draft.status === "failed" ? "destructive" : draft.status === "published" ? "success" : "secondary"}>{STATUS[draft.status] || draft.status}</Badge>
                        <span className="text-xs text-muted-foreground">{draft.source_label} · {categoryLabel(draft.category)} · {draft.confidence || "—"} {draft.has_media ? "· کپشن" : ""}</span>
                        {draft.hashtags && <span className="text-xs text-muted-foreground" dir="ltr">{draft.hashtags}</span>}
                      </div>
                      {edit?.id === draft.id ? (
                        <Textarea value={edit.body} onChange={(event) => setEdit({ ...edit, body: event.target.value })} />
                      ) : <p className="whitespace-pre-wrap text-sm">{draft.body || "متن تولید نشده؛ منبع پایین را ببین."}</p>}
                      {draft.source_content && (
                        <details className="text-xs text-muted-foreground">
                          <summary>متن منبع، جدا از پیش‌نویس</summary>
                          <p className="mt-2 whitespace-pre-wrap">{draft.source_content}</p>
                        </details>
                      )}
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
                      {draft.error && <p className="text-xs text-destructive">{draft.error}</p>}
                      <div className="grid gap-2 lg:grid-cols-3">
                        <Select value={draft.category} disabled={!canEdit} onChange={(event) => run(async () => { await api.patch(`/api/automation/drafts/${draft.id}`, { category: event.target.value }); await load(); }, "دسته ذخیره نشد")} options={CATEGORIES.filter(([value]) => value).map(([value, label]) => ({ value, label }))} />
                        <Input className="h-10" defaultValue={draft.hashtags || ""} disabled={!canEdit} placeholder="#خبر" onBlur={(event) => { if (event.target.value !== (draft.hashtags || "")) run(async () => { await api.patch(`/api/automation/drafts/${draft.id}`, { hashtags: event.target.value }); }, "هشتگ ذخیره نشد"); }} />
                        <Input type="datetime-local" className="h-10" disabled={!canEdit} onChange={(event) => { if (!event.target.value) return; run(async () => { await api.patch(`/api/automation/drafts/${draft.id}`, { scheduled_at: new Date(event.target.value).toISOString() }); await load(); }, "زمان ذخیره نشد"); }} />
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" variant="outline" disabled={!canEdit} onClick={() => setEdit(edit?.id === draft.id ? null : { ...draft })}>{edit?.id === draft.id ? "بستن" : "ویرایش"}</Button>
                        {edit?.id === draft.id && <Button size="sm" variant="brand" onClick={() => run(async () => { await api.patch(`/api/automation/drafts/${draft.id}`, { body: edit.body }); setEdit(null); setMsg("متن ذخیره شد"); await load(); }, "متن ذخیره نشد")}>ذخیره متن</Button>}
                        <Button size="sm" variant="outline" onClick={() => run(async () => { setPreview((await api.get(`/api/automation/drafts/${draft.id}/preview`)).data); }, "پیش‌نمایش نشد")}>خروجی ارسال</Button>
                        {canPublish && <Button size="sm" variant="outline" onClick={() => run(async () => { await api.post(`/api/automation/drafts/${draft.id}/test-send`); setMsg("پیش‌نمایش به خودت رفت، نه کانال"); }, "ارسال آزمایشی نشد")}>بفرست به خودم</Button>}
                        {canPublish && <Button size="sm" variant="outline" onClick={() => run(async () => { await api.post(`/api/automation/drafts/${draft.id}/approve`); setMsg("برای ساعت بعدی زمان‌بندی شد"); await load(); }, "تأیید نشد")}>تأیید</Button>}
                        {canPublish && <Button size="sm" variant="brand" onClick={() => run(async () => { await api.post(`/api/automation/drafts/${draft.id}/publish`); setMsg("منتشر شد"); await load(); }, "منتشر نشد")}>انتشار الان</Button>}
                        {canPublish && draft.published_url && <a className="self-center text-xs underline" href={draft.published_url} target="_blank" rel="noreferrer">پیام کانال</a>}
                        {canPublish && draft.message_id && <Button size="sm" variant="destructive" onClick={() => run(async () => { await api.post(`/api/automation/drafts/${draft.id}/unsend`); setMsg("از کانال حذف شد"); await load(); }, "حذف نشد")}>پس بگیر</Button>}
                        {canEdit && <Button size="sm" variant="outline" onClick={() => run(async () => { setProposal({ id: draft.id, mode: "fresh", ...(await api.post(`/api/automation/drafts/${draft.id}/regenerate?mode=fresh`)).data }); }, "بازنویسی نشد")}>شروع تازه</Button>}
                        {canEdit && <Button size="sm" variant="outline" onClick={() => run(async () => { setProposal({ id: draft.id, mode: "shorter", ...(await api.post(`/api/automation/drafts/${draft.id}/regenerate?mode=shorter`)).data }); }, "کوتاه نشد")}>کوتاه‌تر</Button>}
                        {canEdit && <Button size="sm" variant="outline" onClick={() => run(async () => { setProposal({ id: draft.id, mode: "rewrite", ...(await api.post(`/api/automation/drafts/${draft.id}/regenerate?mode=rewrite`)).data }); }, "چینش عوض نشد")}>چینش تازه</Button>}
                        {draft.status === "skipped" && canEdit && <Button size="sm" variant="outline" onClick={() => run(async () => { await api.post(`/api/automation/drafts/${draft.id}/restore`); await load(); }, "برگردانده نشد")}>برگرداندن</Button>}
                        {canEdit && <Button size="sm" variant="destructive" onClick={() => run(async () => { await api.post(`/api/automation/drafts/${draft.id}/reject`); await load(); }, "رد نشد")}>رد</Button>}
                      </div>
                    </article>
                  ))}
                </div>
              ) : <EmptyState title="پیش‌نویسی نیست" description="بعد از جمع‌آوری، متن ساخته‌شده اینجا دیده می‌شود. تا تأیید یا رسیدن ساعت، در کانال نمی‌رود." />}
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
                <p className="text-sm text-muted-foreground">مثلاً «لحن صمیمی‌تر» یا «پاراگراف آخر را با یک سؤال تمام کن». این متن جای تحلیل‌گر و بازبین را نمی‌گیرد.</p>
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
        {preview && <TelegramPreview html={preview.html_text} plain={preview.text} />}
      </Dialog>
      <Dialog open={!!proposal} onOpenChange={(open) => !open && setProposal(null)} title="تفاوت قبل از جایگزینی" size="lg" footer={proposal?.proposed && <Button variant="brand" onClick={() => run(async () => { await api.patch(`/api/automation/drafts/${proposal.id}`, { body: proposal.proposed }); setProposal(null); setMsg("همان متن تأییدشده جایگزین شد"); await load(); }, "جایگزین نشد")}>جایگزین کن</Button>}>
        {proposal && <><p className="whitespace-pre-wrap text-sm">{proposal.proposed}</p><DiffList rows={proposal.diff} /></>}
      </Dialog>
    </Page>
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
