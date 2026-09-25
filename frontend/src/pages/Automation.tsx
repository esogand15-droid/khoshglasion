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
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DiffList, TelegramPreview } from "@/lib/telegram";

const STATUS: Record<string, string> = {
  preview: "بازبینی",
  scheduled: "زمان‌بندی‌شده",
  published: "منتشر شد",
  rejected: "رد شد",
  failed: "ناموفق",
  skipped: "کنار گذاشته",
  recalled: "پس گرفته شد",
};

const CATEGORIES = [
  ["", "بدون دسته"],
  ["news", "خبر"],
  ["announcement", "اطلاعیه"],
  ["consulting", "مشاوره"],
  ["motivational", "انگیزشی"],
  ["lesson", "آموزشی"],
  ["planning", "برنامه‌ریزی"],
];

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
  }
  useEffect(() => { load().catch(() => setMsg("وضعیت اتوماسیون خوانده نشد")); }, [statusFilter, categoryFilter]);

  async function saveConfig(patch: Record<string, unknown>) {
    await api.patch("/api/automation", patch);
    await load();
  }

  if (!data) return <Page title="پست خودکار" description="در حال خواندن تنظیم واقعی…" />;

  const metrics = data.metrics || {};

  return (
    <Page
      kicker="اتوماسیون"
      title="پست خودکار"
      description="کانال منبع خوانده می‌شود، تکراری حذف می‌شود، پست مستقل ساخته می‌شود و تا تأیید یا کلید انتشار خودکار در صف می‌ماند."
      actions={<Button variant="brand" disabled={busy} onClick={async () => {
        setBusy(true);
        try {
          const { data: result } = await api.post("/api/automation/collect");
          setMsg(result.error || (result.skipped === "disabled" ? "اتوماسیون خاموش است" : `پیش‌نویس تازه: ${result.created ?? 0}`));
          await load();
        } catch (error: any) { setMsg(error.response?.data?.detail || "جمع‌آوری انجام نشد"); }
        finally { setBusy(false); }
      }}>{busy ? "در حال جمع‌آوری" : "جمع‌آوری الان"}</Button>}
    >
      <Alert title="چطور کار می‌کند">
        نشست پرمیوم فقط کانالی را می‌خواند که عمومی است یا اکانت عضو آن است. لینک دعوت خصوصی قبول نیست. متن منبع جدا می‌ماند و کپی نمی‌شود. ایموجی پرمیوم هنگام ارسال از کتابخانهٔ خود پنل می‌آید.
      </Alert>
      {data.last_error && <Alert variant="destructive" title={data.last_error} />}
      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}

      <div className="grid gap-3 sm:grid-cols-4">
        <Card><CardContent className="py-4 text-sm">بازبینی: {metrics.preview ?? 0}</CardContent></Card>
        <Card><CardContent className="py-4 text-sm">زمان‌بندی: {metrics.scheduled ?? 0}</CardContent></Card>
        <Card><CardContent className="py-4 text-sm">امروز: {metrics.published_today ?? 0} از {metrics.daily_cap ?? data.daily_cap ?? 6}</CardContent></Card>
        <Card><CardContent className="py-4 text-sm">ناموفق: {metrics.failed ?? 0}</CardContent></Card>
      </div>

      <Card>
        <CardHeader><CardTitle>انتشار</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <label className="flex items-center justify-between gap-4 rounded-xl border border-border px-4 py-3 text-sm">
            <span>جمع‌آوری خودکار</span>
            <Switch checked={!!data.enabled} onCheckedChange={(value) => saveConfig({ enabled: value })} />
          </label>
          <label className="flex items-center justify-between gap-4 rounded-xl border border-border px-4 py-3 text-sm">
            <span>در ساعت مشخص، بدون تأیید دستی منتشر شود</span>
            <Switch checked={!!data.auto_publish} disabled={!canPublish} onCheckedChange={(value) => saveConfig({ auto_publish: value })} />
          </label>
          <label className="flex items-center justify-between gap-4 rounded-xl border border-border px-4 py-3 text-sm">
            <span>توقف اضطراری صف</span>
            <Switch checked={!!data.paused} onCheckedChange={(value) => saveConfig({ paused: value })} />
          </label>
          <label className="flex items-center justify-between gap-4 rounded-xl border border-border px-4 py-3 text-sm">
            <span>تعادل دسته در سقف روزانه</span>
            <Switch checked={data.balance_categories !== false} onCheckedChange={(value) => saveConfig({ balance_categories: value })} />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="سقف انتشار روزانه">
              <Input type="number" min={1} max={48} defaultValue={data.daily_cap || 6} onBlur={(event) => saveConfig({ daily_cap: Number(event.target.value) || 6 })} />
            </Field>
            <Field label="ذکر منبع">
              <select
                className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm"
                value={data.attribution_mode || "news"}
                onChange={(event) => saveConfig({ attribution_mode: event.target.value })}
              >
                <option value="news">فقط خبر و اطلاعیه</option>
                <option value="always">همیشه</option>
                <option value="never">هرگز</option>
              </select>
            </Field>
          </div>
          <Field label="کانال مقصد">
            <select
              className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm"
              value={data.target_chat_id || ""}
              onChange={(event) => saveConfig({ target_chat_id: event.target.value ? Number(event.target.value) : null })}
            >
              <option value="">انتخاب نشده</option>
              {channels.map((channel) => (
                <option key={channel.id} value={channel.chat_id}>{channel.title || channel.username || channel.chat_id}</option>
              ))}
            </select>
          </Field>
          <p className="text-xs text-muted-foreground">ساعت بعدی: {data.next_slot ? new Date(data.next_slot).toLocaleString("fa-IR") : "ساعتی ثبت نشده"}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>کانال‌های منبع</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Input dir="ltr" value={source} onChange={(event) => setSource(event.target.value)} placeholder="@channel یا https://t.me/channel" />
            <select className="h-10 rounded-xl border border-border bg-background px-3 text-sm" value={sourceCategory} onChange={(event) => setSourceCategory(event.target.value)}>
              {CATEGORIES.map(([value, label]) => <option key={value || "none"} value={value}>{label}</option>)}
            </select>
            <Button variant="outline" onClick={async () => {
              try {
                await api.post("/api/automation/sources", { username: source, category_hint: sourceCategory || null });
                setSource("");
                await load();
              } catch (error: any) { setMsg(error.response?.data?.detail || "منبع ثبت نشد"); }
            }}>افزودن</Button>
          </div>
          {data.sources?.length ? (
            <Table>
              <TableHeader><TableRow><TableHead>منبع</TableHead><TableHead>اولویت و فاصله</TableHead><TableHead>وضعیت</TableHead><TableHead /></TableRow></TableHeader>
              <TableBody>
                {data.sources.map((item: any) => (
                  <TableRow key={item.id}>
                    <TableCell dir="ltr">{item.username}</TableCell>
                    <TableCell>
                      <select className="h-8 rounded-lg border border-border bg-background px-2 text-xs" value={item.priority || "normal"} disabled={!canEdit} onChange={async (event) => { await api.patch(`/api/automation/sources/${item.id}`, { priority: event.target.value }); load(); }}>
                        <option value="high">بالا</option>
                        <option value="normal">معمولی</option>
                        <option value="low">پایین</option>
                      </select>
                      <Input className="mt-1 h-8" type="number" min={5} defaultValue={item.interval_minutes || 20} disabled={!canEdit} onBlur={async (event) => { await api.patch(`/api/automation/sources/${item.id}`, { interval_minutes: Number(event.target.value) || 20 }); }} />
                    </TableCell>
                    <TableCell>{item.last_error || `تا پیام ${item.last_message_id || 0}`}</TableCell>
                    <TableCell className="space-x-1 space-x-reverse">
                      <Switch checked={item.enabled !== false} disabled={!canEdit} onCheckedChange={async (value) => { await api.patch(`/api/automation/sources/${item.id}`, { enabled: value }); load(); }} />
                      <Button size="sm" variant="outline" disabled={!canEdit} onClick={async () => { try { const { data: probe } = await api.post(`/api/automation/sources/${item.id}/probe`); setMsg(probe.readable ? "منبع باز شد" : probe.last_error); await load(); } catch (error: any) { setMsg(error.response?.data?.detail || "آزمایش نشد"); } }}>آزمایش</Button>
                      <Button size="sm" variant="destructive" disabled={!canEdit} onClick={async () => { await api.delete(`/api/automation/sources/${item.id}`); load(); }}>حذف</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : <EmptyState title="منبعی نیست" description="یک کانال عمومی خبری یا مشاوره‌ای اضافه کن." />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>ساعت انتشار، به وقت تهران</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Input type="number" min={0} max={23} value={hour} onChange={(event) => setHour(event.target.value)} />
            <Input type="number" min={0} max={59} value={minute} onChange={(event) => setMinute(event.target.value)} />
            <select className="h-10 rounded-xl border border-border bg-background px-3 text-sm" value={slotCategory} onChange={(event) => setSlotCategory(event.target.value)}>
              {CATEGORIES.map(([value, label]) => <option key={value || "any"} value={value}>{label}</option>)}
            </select>
            <Button variant="outline" onClick={async () => { await api.post("/api/automation/slots", { hour: Number(hour), minute: Number(minute), category: slotCategory || null }); load(); }}>ساعت تازه</Button>
          </div>
          {data.slots?.length ? data.slots.map((slot: any) => (
            <div key={slot.id} className="flex items-center justify-between rounded-xl border border-border px-4 py-2 text-sm">
              <span>{String(slot.hour).padStart(2, "0")}:{String(slot.minute).padStart(2, "0")} {slot.category ? `· ${slot.category}` : ""}</span>
              <span className="flex items-center gap-2">
                <Switch checked={slot.enabled !== false} disabled={!canEdit} onCheckedChange={async (value) => { await api.patch(`/api/automation/slots/${slot.id}`, { enabled: value }); load(); }} />
                <Button size="sm" variant="destructive" disabled={!canEdit} onClick={async () => { await api.delete(`/api/automation/slots/${slot.id}`); load(); }}>حذف</Button>
              </span>
            </div>
          )) : <EmptyState title="ساعتی نیست" description="مثلاً ۹ صبح برای خبر و ۶ عصر برای مشاوره." />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>هشتگ‌های رسمی</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {(data.hashtags || []).map((tag: any) => (
            <Button
              key={tag.id}
              size="sm"
              variant={tag.enabled && !tag.forbidden ? "brand" : "outline"}
              onClick={async () => { await api.patch(`/api/automation/hashtags/${tag.id}`, { enabled: !tag.enabled }); load(); }}
            >
              #{tag.tag}
            </Button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>پیش‌نویس‌ها</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <select className="h-10 rounded-xl border border-border bg-background px-3 text-sm" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="">همه وضعیت‌ها</option>
              {Object.entries(STATUS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <select className="h-10 rounded-xl border border-border bg-background px-3 text-sm" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
              {CATEGORIES.map(([value, label]) => <option key={value || "all"} value={value}>{label}</option>)}
            </select>
          </div>
          {data.drafts?.length ? (
            <div className="space-y-4">
              {data.drafts.map((draft: any) => (
                <article key={draft.id} className="space-y-2 rounded-xl border border-border p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge>{STATUS[draft.status] || draft.status}</Badge>
                    <span className="text-xs text-muted-foreground">{draft.source_label} · {draft.category} · {draft.confidence || "—"} {draft.has_media ? "· کپشن" : ""}</span>
                    {draft.hashtags && <span className="text-xs text-muted-foreground">{draft.hashtags}</span>}
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
                          <p>نسخه {item.version} · {item.reason}</p>
                          <p className="whitespace-pre-wrap">{item.body}</p>
                          {canEdit && <Button size="sm" variant="outline" onClick={async () => { await api.post(`/api/automation/drafts/${draft.id}/restore-version?version=${item.version}`); load(); }}>برگرداندن این نسخه</Button>}
                        </div>
                      ))}
                    </details>
                  ) : null}
                  {draft.error && <p className="text-xs text-destructive">{draft.error}</p>}
                  <div className="flex flex-wrap gap-2">
                    <select className="h-8 rounded-lg border border-border bg-background px-2 text-xs" value={draft.category} disabled={!canEdit} onChange={async (event) => { await api.patch(`/api/automation/drafts/${draft.id}`, { category: event.target.value }); load(); }}>
                      {CATEGORIES.filter(([value]) => value).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                    <Input className="h-8 max-w-xs" defaultValue={draft.hashtags || ""} disabled={!canEdit} placeholder="#خبر" onBlur={async (event) => { if (event.target.value !== (draft.hashtags || "")) await api.patch(`/api/automation/drafts/${draft.id}`, { hashtags: event.target.value }); }} />
                    <Input type="datetime-local" className="h-8 max-w-[220px]" disabled={!canEdit} onChange={async (event) => {
                      if (!event.target.value) return;
                      await api.patch(`/api/automation/drafts/${draft.id}`, { scheduled_at: new Date(event.target.value).toISOString() });
                      load();
                    }} />
                    <Button size="sm" variant="outline" disabled={!canEdit} onClick={() => setEdit(edit?.id === draft.id ? null : { ...draft })}>{edit?.id === draft.id ? "بستن" : "ویرایش"}</Button>
                    {edit?.id === draft.id && <Button size="sm" variant="brand" onClick={async () => { await api.patch(`/api/automation/drafts/${draft.id}`, { body: edit.body }); setEdit(null); load(); }}>ذخیره متن</Button>}
                    <Button size="sm" variant="outline" onClick={async () => { try { setPreview((await api.get(`/api/automation/drafts/${draft.id}/preview`)).data); } catch (error: any) { setMsg(error.response?.data?.detail || "پیش‌نمایش نشد"); } }}>خروجی ارسال</Button>
                    {canPublish && <Button size="sm" variant="outline" onClick={async () => { try { await api.post(`/api/automation/drafts/${draft.id}/test-send`); setMsg("پیش‌نمایش به خودت رفت، نه کانال"); } catch (error: any) { setMsg(error.response?.data?.detail || "ارسال آزمایشی نشد"); } }}>بفرست به خودم</Button>}
                    {canPublish && <Button size="sm" variant="outline" onClick={async () => { try { await api.post(`/api/automation/drafts/${draft.id}/approve`); setMsg("برای ساعت بعدی زمان‌بندی شد"); await load(); } catch (error: any) { setMsg(error.response?.data?.detail || "تأیید نشد"); } }}>تأیید</Button>}
                    {canPublish && <Button size="sm" variant="brand" onClick={async () => {
                      try { await api.post(`/api/automation/drafts/${draft.id}/publish`); setMsg("منتشر شد"); await load(); }
                      catch (error: any) { setMsg(error.response?.data?.detail || "منتشر نشد"); }
                    }}>انتشار الان</Button>}
                    {canPublish && draft.published_url && <a className="text-xs underline" href={draft.published_url} target="_blank" rel="noreferrer">پیام کانال</a>}
                    {canPublish && draft.message_id && <Button size="sm" variant="destructive" onClick={async () => { try { await api.post(`/api/automation/drafts/${draft.id}/unsend`); setMsg("از کانال حذف شد"); await load(); } catch (error: any) { setMsg(error.response?.data?.detail || "حذف نشد"); } }}>پس بگیر</Button>}
                    {canEdit && <Button size="sm" variant="outline" onClick={async () => { try { setProposal({ id: draft.id, mode: "fresh", ...(await api.post(`/api/automation/drafts/${draft.id}/regenerate?mode=fresh`)).data }); } catch (error: any) { setMsg(error.response?.data?.detail || "بازنویسی نشد"); } }}>بازنویسی</Button>}
                    {draft.status === "skipped" && canEdit && <Button size="sm" variant="outline" onClick={async () => { await api.post(`/api/automation/drafts/${draft.id}/restore`); load(); }}>برگرداندن</Button>}
                    {canEdit && <Button size="sm" variant="destructive" onClick={async () => { await api.post(`/api/automation/drafts/${draft.id}/reject`); load(); }}>رد</Button>}
                  </div>
                </article>
              ))}
            </div>
          ) : <EmptyState title="پیش‌نویسی نیست" description="بعد از جمع‌آوری، متن ساخته‌شده اینجا دیده می‌شود. تا تأیید یا رسیدن ساعت، در کانال نمی‌رود." />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>پرامپت‌های فعال، فقط خواندنی</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {(data.prompts || []).map((item: any) => (
            <details key={item.name} className="rounded-xl border border-border p-3 text-sm">
              <summary>{item.name} · نسخه {item.version}</summary>
              <pre className="mt-2 whitespace-pre-wrap text-xs text-muted-foreground">{item.body}</pre>
            </details>
          ))}
        </CardContent>
      </Card>

      <Dialog open={!!preview} onOpenChange={(open) => !open && setPreview(null)} title="خروجی قبل از کانال" size="lg">
        {preview && <TelegramPreview html={preview.html_text} plain={preview.text} />}
      </Dialog>
      <Dialog open={!!proposal} onOpenChange={(open) => !open && setProposal(null)} title="تفاوت قبل از جایگزینی" size="lg" footer={proposal?.proposed && <Button variant="brand" onClick={async () => { await api.patch(`/api/automation/drafts/${proposal.id}`, { body: proposal.proposed }); setProposal(null); setMsg("همان متن تأییدشده جایگزین شد"); load(); }}>جایگزین کن</Button>}>
        {proposal && <><p className="whitespace-pre-wrap text-sm">{proposal.proposed}</p><DiffList rows={proposal.diff} /></>}
      </Dialog>

      <Card>
        <CardHeader><CardTitle>لاگ صف</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-xs text-muted-foreground">
          {(data.logs || []).length ? data.logs.map((item: any, index: number) => (
            <p key={`${item.event}-${index}`}>{item.event} {item.detail ? `· ${item.detail}` : ""}</p>
          )) : <p>هنوز رویدادی ثبت نشده.</p>}
        </CardContent>
      </Card>
    </Page>
  );
}
