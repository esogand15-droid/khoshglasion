import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import SessionLogin from "../components/SessionLogin";
import { Page } from "../components/page";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { FileUpload } from "@/components/ui/file-upload";
import { PasswordInput } from "@/components/ui/password-input";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

function SettingSwitch({ checked, label, onChange, disabled }: { checked: boolean; label: string; onChange: (value: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex items-center justify-between gap-4 rounded-xl border border-border px-4 py-3 text-sm">
      <span>{label}</span>
      <Switch checked={checked} disabled={disabled} onCheckedChange={onChange} />
    </label>
  );
}

export default function Settings() {
  const [data, setData] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [aiTest, setAiTest] = useState<any>(null);
  const [testing, setTesting] = useState(false);
  const [password, setPassword] = useState({ current_password: "", new_password: "" });
  const [adminForm, setAdminForm] = useState({ username: "", password: "", role: "ADMIN" });
  const [params, setParams] = useSearchParams();
  const role = useAuth((state) => state.role);
  const canEdit = !role || role !== "VIEWER";
  const canOwn = !role || role === "OWNER";
  const canConnect = !role || role === "OWNER" || role === "ADMIN";
  const tab = ["run", "ai", "look", "session", "access", "problems"].includes(params.get("tab") || "") ? params.get("tab")! : "run";

  async function load() { setData((await api.get("/api/system/settings")).data); }
  useEffect(() => { load().catch(() => {}); }, []);

  async function save(partial: any) {
    try {
      setData({ ...data, ...(await api.post("/api/system/settings", partial)).data });
      setMsg("ذخیره شد و بدون ری‌استارت اعمال می‌شود.");
    } catch (error: any) {
      setMsg(error.response?.data?.detail || "ذخیره نشد");
      load();
    }
  }
  if (!data) return <Spinner label="در حال بارگذاری تنظیم‌ها" />;

  return (
    <Page kicker="کنترل زنده" title="اتاق تنظیم">
      {msg && <Alert>{msg}</Alert>}
      {!canEdit && <Alert>این نقش فقط می‌تواند تنظیم‌ها را ببیند.</Alert>}
      <Tabs value={tab} defaultValue="run" onValueChange={(value) => setParams({ tab: value })}>
        <TabsList aria-label="بخش تنظیمات">
          <TabsTrigger value="run">پردازش</TabsTrigger>
          <TabsTrigger value="ai">هوش مصنوعی</TabsTrigger>
          <TabsTrigger value="look">ظاهر پست</TabsTrigger>
          <TabsTrigger value="session">نشست</TabsTrigger>
          <TabsTrigger value="access">دسترسی</TabsTrigger>
          <TabsTrigger value="problems">مشکلات</TabsTrigger>
        </TabsList>
        <TabsContent value="run">
          <div className="grid gap-2">
            <SettingSwitch disabled={!canEdit} checked={data.dry_run} label="حالت آزمایشی (ادیت واقعی نمی‌شود)" onChange={(v) => save({ dry_run: v })} />
            <SettingSwitch disabled={!canEdit} checked={data.kill_switch} label="توقف اضطراری" onChange={(v) => save({ kill_switch: v })} />
            <SettingSwitch disabled={!canEdit} checked={data.auto_register_channels} label="ثبت خودکار کانال وقتی ربات ادمین می‌شود" onChange={(v) => save({ auto_register_channels: v })} />
            <SettingSwitch disabled={!canEdit} checked={data.reprocess_edits} label="بازنویسی اگر ادمین بعداً پست را ادیت کرد" onChange={(v) => save({ reprocess_edits: v })} />
            <SettingSwitch disabled={!canEdit} checked={data.persian_normalize} label="یکسان‌سازی ی و ک فارسی" onChange={(v) => save({ persian_normalize: v })} />
            <SettingSwitch disabled={!canEdit} checked={data.preserve_links} label="حفظ لینک، منشن و هشتگ" onChange={(v) => save({ preserve_links: v })} />
          </div>
        </TabsContent>
        <TabsContent value="ai">
          <Card>
            <CardHeader><CardTitle>هوش مصنوعی</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <SettingSwitch disabled={!canEdit} checked={data.ai_enabled} label="بازنویسی هوشمند" onChange={(v) => save({ ai_enabled: v })} />
              <p className="text-xs text-muted-foreground">پست‌های معمولی به مدل فرستاده می‌شوند. گزینه و پاسخ آزمون، و متن کوتاه‌تر از حداقل کاراکتر، دست نمی‌خورند. اگر مدل عدد یا نقل‌قول را بیندازد، همان متن ادمین می‌ماند و در پیام‌ها علتش نوشته می‌شود.</p>
              <Field label="Base URL"><Input dir="ltr" value={data.ai_base_url || ""} onChange={(e) => setData({ ...data, ai_base_url: e.target.value })} placeholder="https://integrate.api.nvidia.com/v1" /></Field>
              <p className="text-xs text-muted-foreground">برای NVIDIA همین را بگذار: https://integrate.api.nvidia.com/v1 — سیستم خودش /chat/completions را اضافه می‌کند. درخواست واقعی: {data.ai_endpoint || "بعد از ذخیره دیده می‌شود"} · provider: {data.ai_provider || "—"}</p>
              <Field label="Model"><Input dir="ltr" value={data.ai_model || ""} onChange={(e) => setData({ ...data, ai_model: e.target.value })} placeholder="openai/gpt-oss-20b" /></Field>
              <div className="grid gap-3 md:grid-cols-3">
                <Field label="دما"><Input type="number" min={0} max={1.5} step={0.1} value={data.ai_temperature ?? 0.7} onChange={(e) => setData({ ...data, ai_temperature: e.target.value })} /></Field>
                <Field label="سقف توکن"><Input type="number" min={64} max={4000} value={data.ai_max_tokens ?? 1800} onChange={(e) => setData({ ...data, ai_max_tokens: e.target.value })} /></Field>
                <Field label="حداقل کاراکتر"><Input type="number" min={0} max={500} value={data.ai_min_chars ?? 40} onChange={(e) => setData({ ...data, ai_min_chars: e.target.value })} /></Field>
              </div>
              <Field label={`کلید API ${data.ai_api_key_masked || ""}`}>
                <PasswordInput placeholder="خالی = بدون تغییر" onChange={(e) => setData({ ...data, ai_api_key: e.target.value })} />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button variant="brand" disabled={!canEdit} onClick={() => save({ ai_enabled: data.ai_enabled, ai_base_url: data.ai_base_url, ai_model: data.ai_model, ai_api_key: data.ai_api_key || undefined, ai_temperature: Number(data.ai_temperature), ai_max_tokens: Number(data.ai_max_tokens), ai_min_chars: Number(data.ai_min_chars) })}>ذخیره AI</Button>
                <Button variant="outline" disabled={testing || !canEdit} onClick={async () => {
                  setTesting(true);
                  setAiTest(null);
                  try {
                    await save({ ai_enabled: data.ai_enabled, ai_base_url: data.ai_base_url, ai_model: data.ai_model, ai_api_key: data.ai_api_key || undefined });
                    const { data: result } = await api.post("/api/system/ai/test");
                    setAiTest(result);
                    setMsg(result.ok ? `اتصال برقرار شد · ${result.provider} · ${result.latency_ms}ms` : result.error);
                  } catch (error: any) {
                    setMsg(error.response?.data?.detail || error.message || "تست انجام نشد");
                  } finally {
                    setTesting(false);
                  }
                }}>{testing ? <Spinner size="sm" label="در حال تست" /> : "تست اتصال"}</Button>
              </div>
              {aiTest && (
                <Alert variant={aiTest.ok ? "success" : "destructive"} title={aiTest.ok ? `مدل جواب داد: ${aiTest.sample || "سلام"}` : aiTest.error}>
                  {aiTest.provider} · {aiTest.endpoint}{aiTest.latency_ms ? ` · ${aiTest.latency_ms}ms` : ""}
                </Alert>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="look">
          <Card>
            <CardContent className="grid gap-3 pt-5 md:grid-cols-2">
              <Field label="حالت ایموجی">
                <Select
                  value={data.premium_mode}
                  disabled={!canEdit}
                  onChange={(e) => save({ premium_mode: e.target.value })}
                  options={[
                    { value: "auto", label: "خودکار: فقط نشست پرمیوم؛ اگر نشد ادیت نمی‌شود" },
                    { value: "bot", label: "Bot API با ایموجی پرمیوم، بدون متن ساده" },
                    { value: "user", label: "فقط نشست پرمیوم" },
                    { value: "off", label: "بدون ایموجی پرمیوم" },
                  ]}
                />
              </Field>
              <Field label="سقف ایموجی در هر پست"><Input disabled={!canEdit} type="number" value={data.max_emoji_per_post} onChange={(e) => setData({ ...data, max_emoji_per_post: e.target.value })} onBlur={() => save({ max_emoji_per_post: Number(data.max_emoji_per_post) })} /></Field>
              <Field label="تأخیر ادیت (ثانیه)"><Input disabled={!canEdit} type="number" value={data.edit_delay_seconds} onChange={(e) => setData({ ...data, edit_delay_seconds: e.target.value })} onBlur={() => save({ edit_delay_seconds: Number(data.edit_delay_seconds) })} /></Field>
              <Field label="آیدی ادمین‌های تلگرام"><Input disabled={!canEdit} dir="ltr" value={data.admin_telegram_ids || ""} onChange={(e) => setData({ ...data, admin_telegram_ids: e.target.value })} onBlur={() => save({ admin_telegram_ids: data.admin_telegram_ids })} placeholder="123,456" /></Field>
              <Field label="چت اعلان خطا"><Input disabled={!canEdit} dir="ltr" value={data.notify_chat_id || ""} onChange={(e) => setData({ ...data, notify_chat_id: e.target.value })} onBlur={() => save({ notify_chat_id: data.notify_chat_id })} /></Field>
              <Field label="لینک عضویت"><Input disabled={!canEdit} dir="ltr" value={data.footer_url || ""} onChange={(e) => setData({ ...data, footer_url: e.target.value })} onBlur={() => save({ footer_url: data.footer_url })} placeholder="https://t.me/Rotbeland1" /></Field>
              <Field label="یوزرنیم پشتیبانی"><Input disabled={!canEdit} dir="ltr" value={data.support_username || ""} onChange={(e) => setData({ ...data, support_username: e.target.value })} onBlur={() => save({ support_username: data.support_username })} placeholder="Rotbeland_support" /></Field>
              <Field label="فوتر پیش‌فرض سراسری"><Textarea disabled={!canEdit} value={data.default_footer || ""} onChange={(e) => setData({ ...data, default_footer: e.target.value })} onBlur={() => save({ default_footer: data.default_footer })} /></Field>
            </CardContent>
          </Card>
          <p className="mt-3 text-xs text-muted-foreground">وضعیت نشست: {data.user_session_configured ? "وصل است" : "هنوز وصل نیست"}. ورود شماره و کد در تب نشست است، نه در متغیر Railway.</p>
        </TabsContent>
        <TabsContent value="problems">
          <ProblemsTab canEdit={canEdit} canOwn={canOwn} canConnect={canConnect} onDone={(text) => { setMsg(text); load(); }} />
        </TabsContent>
        <TabsContent value="session">
          {canConnect ? <SessionLogin premiumMode={data.premium_mode} onChange={load} /> : <Alert>فقط مالک یا ادمین می‌تواند نشست پرمیوم را وصل کند.</Alert>}
        </TabsContent>
        <TabsContent value="access">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>رمز پنل</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Field label="رمز فعلی"><PasswordInput autoComplete="current-password" value={password.current_password} onChange={(e) => setPassword({ ...password, current_password: e.target.value })} /></Field>
                <Field label="رمز جدید، حداقل ۸ کاراکتر"><PasswordInput strength autoComplete="new-password" value={password.new_password} onChange={(e) => setPassword({ ...password, new_password: e.target.value })} /></Field>
                <Button variant="outline" onClick={async () => { try { await api.post("/api/auth/password", password); setMsg("رمز عوض شد"); } catch (e: any) { setMsg(e.response?.data?.detail || "عوض نشد"); } }}>تغییر رمز</Button>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>ادمین تازه و پشتیبان</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Field label="نام کاربری"><Input autoComplete="off" value={adminForm.username} onChange={(e) => setAdminForm({ ...adminForm, username: e.target.value })} /></Field>
                <Field label="رمز"><PasswordInput autoComplete="new-password" value={adminForm.password} onChange={(e) => setAdminForm({ ...adminForm, password: e.target.value })} /></Field>
                <Field label="نقش">
                  <Select value={adminForm.role} onChange={(e) => setAdminForm({ ...adminForm, role: e.target.value })} options={[
                    { value: "ADMIN", label: "ادمین، می‌تواند منتشر کند" },
                    { value: "EDITOR", label: "ویرایشگر، بدون انتشار" },
                    { value: "VIEWER", label: "فقط بیننده" },
                  ]} />
                </Field>
                <Button variant="outline" disabled={!canOwn} onClick={async () => { try { await api.post("/api/system/admins", adminForm); setMsg("ادمین ساخته شد"); } catch (e: any) { setMsg(e.response?.data?.detail || "ساخته نشد"); } }}>ساخت ادمین</Button>
                <Separator label="پشتیبان" />
                <Button variant="outline" disabled={!canOwn} onClick={async () => { try { const { data: backup } = await api.get("/api/system/backup"); const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "khoshgelasion-backup.json"; a.click(); } catch (e: any) { setMsg(e.response?.data?.detail || "پشتیبان گرفته نشد"); } }}>دانلود پشتیبان</Button>
                {canOwn && <FileUpload
                  accept="application/json"
                  multiple={false}
                  hint="فایل JSON پشتیبان"
                  onFiles={async (files) => {
                    const file = files[0];
                    if (!file) return;
                    const payload = JSON.parse(await file.text());
                    const { data: restored } = await api.post("/api/system/restore", payload);
                    setMsg(`بازیابی شد: ${JSON.stringify(restored.restored)}`);
                    load();
                  }}
                />}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </Page>
  );
}

function ProblemsTab({ canEdit, canOwn, canConnect, onDone }: { canEdit: boolean; canOwn: boolean; canConnect: boolean; onDone: (text: string) => void }) {
  const setAuth = useAuth((state) => state.setAuth);
  const username = useAuth((state) => state.username);
  const role = useAuth((state) => state.role);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [token, setToken] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [password, setPassword] = useState({ current_password: "", new_password: "" });
  const [busy, setBusy] = useState("");

  useEffect(() => {
    api.get("/api/system/overview").then((response) => setAlerts(response.data.alerts || [])).catch(() => {});
  }, [busy]);

  async function repair(action: string, extra: Record<string, unknown> = {}) {
    setBusy(action);
    try {
      const { data } = await api.post("/api/system/repairs", { action, ...extra });
      if (data.token && username && role) setAuth(data.token, username, role);
      const fallback = data.username ? `ربات @${data.username} وصل شد` : "انجام شد";
      onDone(data.message || fallback);
      setToken("");
    } catch (error: any) {
      onDone(error.response?.data?.detail || "انجام نشد");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="space-y-4">
      <Alert title="همهٔ این‌ها از داخل پنل بسته می‌شود">
        لازم نیست برای این خطاها روی سرور دستور بزنی. هر مورد دکمهٔ خودش را دارد. فقط عوض کردن نوع دیتابیس وسط اجرا ممکن نیست، چون برنامه قبل از پنل به دیتابیس وصل می‌شود.
      </Alert>
      {alerts.map((item) => (
        <Alert key={item.code} variant={item.level === "danger" ? "destructive" : item.level === "info" ? "info" : "warning"}>
          {item.text}
          {item.fix_path && item.fix_path !== "/settings?tab=problems" && (
            <Link className="mt-2 block font-medium underline" to={item.fix_path}>{item.fix_label}</Link>
          )}
        </Alert>
      ))}
      <Card>
        <CardHeader><CardTitle>توکن ربات</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Field label="توکن BotFather"><PasswordInput value={token} disabled={!canOwn} onChange={(event) => setToken(event.target.value)} autoComplete="off" /></Field>
          <Button variant="brand" disabled={!canOwn || busy === "bot_token" || token.trim().length < 20} onClick={() => repair("bot_token", { bot_token: token.trim() })}>ذخیره و آزمایش توکن</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>وبهوک</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Field label="آدرس عمومی، اگر دامنه خودش پیدا نشد"><Input dir="ltr" value={webhookUrl} disabled={!canConnect} onChange={(event) => setWebhookUrl(event.target.value)} placeholder="https://example.com/telegram/webhook" /></Field>
          <div className="flex flex-wrap gap-2">
            <Button variant="brand" disabled={!canConnect || !!busy} onClick={() => repair("webhook", { webhook_url: webhookUrl || undefined, regenerate_secret: true })}>ساخت رمز و ثبت وبهوک</Button>
            <Button variant="outline" disabled={!canConnect || !!busy} onClick={() => repair("webhook", { webhook_url: webhookUrl || undefined })}>ثبت با رمز فعلی</Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>رمز پنل و کلید ورود</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">اگر هشدار «رمز ادمین یا JWT هنوز پیش‌فرض است» را می‌بینی، هر دو را همین‌جا عوض کن. ساخت کلید تازه این نشست را نگه می‌دارد و بقیه را خارج می‌کند.</p>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="رمز فعلی"><PasswordInput autoComplete="current-password" value={password.current_password} onChange={(event) => setPassword({ ...password, current_password: event.target.value })} /></Field>
            <Field label="رمز جدید، حداقل ۸ کاراکتر"><PasswordInput strength autoComplete="new-password" value={password.new_password} onChange={(event) => setPassword({ ...password, new_password: event.target.value })} /></Field>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="brand" disabled={!!busy || password.new_password.length < 8} onClick={async () => {
              setBusy("password");
              try {
                await api.post("/api/auth/password", password);
                setPassword({ current_password: "", new_password: "" });
                onDone("رمز پنل عوض شد");
              } catch (error: any) {
                onDone(error.response?.data?.detail || "رمز عوض نشد");
              } finally {
                setBusy("");
              }
            }}>عوض کردن رمز پنل</Button>
            <Button variant="outline" disabled={!canOwn || !!busy} onClick={() => repair("rotate_jwt")}>ساخت کلید ورود</Button>
            <Button variant="outline" disabled={!canEdit || !!busy} onClick={() => repair("clear_emoji_error")}>پاک کردن خطای ایموجی</Button>
            <Link className="self-center text-sm underline" to="/settings?tab=run">توقف و حالت آزمایشی</Link>
            <Link className="self-center text-sm underline" to="/settings?tab=ai">هوش مصنوعی</Link>
            <Link className="self-center text-sm underline" to="/settings?tab=session">نشست پرمیوم</Link>
            <Link className="self-center text-sm underline" to="/channels">کانال‌ها</Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
