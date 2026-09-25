import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Alert } from "@/components/ui/alert";
import { useConfirm } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { OtpField } from "@/components/ui/otp-field";
import { PasswordInput } from "@/components/ui/password-input";
import { Select } from "@/components/ui/select";
import { LoadError, PageSkeleton } from "@/components/ui/page-state";
import { Switch } from "@/components/ui/switch";
import { en } from "@/lib/utils";

type Account = {
  id: string;
  label: string | null;
  phone_masked: string;
  user_id: number | null;
  username: string | null;
  premium: boolean | null;
  roles: string[];
  enabled: boolean;
  join_public: boolean;
  last_error?: string | null;
  authorized?: boolean;
};

type Status = {
  configured: boolean;
  source: string | null;
  pending_step: "code" | "password" | null;
  phone_masked: string;
  delivery: string | null;
  code_length: number | null;
  user_id: number | null;
  username: string | null;
  premium: boolean | null;
  authorized?: boolean;
  accounts?: Account[];
};

function detailOf(error: any) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "ورودی را کامل کن.";
  return error?.message || "انجام نشد";
}

export default function SessionLogin({ premiumMode, onChange }: { premiumMode?: string; onChange?: () => void }) {
  const role = useAuth((state) => state.role);
  const canWrite = role === "OWNER" || role === "ADMIN" || !role;
  const [status, setStatus] = useState<Status | null>(null);
  const [form, setForm] = useState({ api_id: "", api_hash: "", phone: "", roles: "both", label: "" });
  const [joinName, setJoinName] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const { ask, dialog } = useConfirm();

  async function load() {
    setStatus((await api.get("/api/system/telegram-session")).data);
  }
  useEffect(() => { load().catch((error) => setMsg(detailOf(error))); }, []);

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setMsg("");
    try {
      await work();
      await load();
      onChange?.();
    } catch (error) {
      setMsg(detailOf(error));
    } finally {
      setBusy(false);
    }
  }

  if (!status) {
    return msg
      ? <LoadError title={msg} onRetry={() => load().catch((error) => setMsg(detailOf(error)))} />
      : <PageSkeleton variant="form" />;
  }
  const step = status.pending_step;
  const accounts = status.accounts || [];
  const modeBlocks = premiumMode === "bot" || premiumMode === "off";
  const codeLength = status.code_length && status.code_length >= 4 && status.code_length <= 8 ? status.code_length : null;

  function patch(account: Account, body: Record<string, unknown>) {
    return run(async () => { await api.patch(`/api/system/telegram-sessions/${account.id}`, body); });
  }

  return (
    <Card>
      {dialog}
      <CardHeader>
        <CardTitle>نشست‌های تلگرام</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          چند اکانت می‌توانند هم‌زمان وصل باشند. اکانت پرمیوم ایموجی متحرک کانال را ادیت می‌کند. اکانت معمولی در کانال‌های عمومی خبری عضو می‌شود و خبر جمع می‌کند. اگر بخواهی، همان اکانت پرمیوم هر دو کار را انجام می‌دهد. لینک خصوصی جوین نمی‌شود. اگر اکانت خبر از قبل عضو است، همان لینک را اینجا یا در منابع بگذار تا فقط خوانده شود.
        </p>
        {modeBlocks && (
          <Alert variant="warning" title="حالت ایموجی این نشست را استفاده نمی‌کند">
            الان روی {premiumMode === "off" ? "بدون ایموجی" : "فقط Bot API"} است. برای خط طلایی، در تب ظاهر پست حالت را بگذار روی خودکار یا فقط نشست پرمیوم.
          </Alert>
        )}
        {msg && <Alert variant="destructive">{msg}</Alert>}

        {accounts.map((account, index) => (
          <div key={account.id} className="space-y-3 rounded-xl border border-border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={account.enabled ? "success" : "warning"}>{account.enabled ? "روشن" : "خاموش"}</Badge>
              {account.premium === true && <Badge variant="brand">پرمیوم</Badge>}
              {account.premium === false && <Badge variant="warning">معمولی</Badge>}
              {account.roles.includes("emoji") && <Badge>ایموجی</Badge>}
              {account.roles.includes("news") && <Badge>خبر</Badge>}
              <span className="text-sm">{account.label || `نشست ${index + 1}`}</span>
              {account.username && <span dir="ltr" className="text-sm">@{account.username}</span>}
              {account.phone_masked && <span dir="ltr" className="text-xs text-muted-foreground">{account.phone_masked}</span>}
            </div>
            {account.premium === false && account.roles.includes("emoji") && (
              <Alert variant="warning">این اکانت پرمیوم نیست. خط طلایی را نشان نمی‌دهد، ولی می‌تواند خبر جمع کند.</Alert>
            )}
            {account.last_error && <Alert variant="warning">{account.last_error}</Alert>}
            {canWrite && (
              <div className="grid gap-2">
                <label className="flex items-center justify-between gap-3 text-sm">
                  <span>ادیت ایموجی متحرک</span>
                  <Switch checked={account.roles.includes("emoji")} disabled={busy} onCheckedChange={(on) => {
                    const roles = new Set(account.roles);
                    if (on) roles.add("emoji"); else roles.delete("emoji");
                    if (!roles.size) return setMsg("حداقل یک نقش لازم است");
                    patch(account, { roles: [...roles].join(",") });
                  }} />
                </label>
                <label className="flex items-center justify-between gap-3 text-sm">
                  <span>جمع‌آوری خبر و عضویت در کانال عمومی</span>
                  <Switch checked={account.roles.includes("news")} disabled={busy} onCheckedChange={(on) => {
                    const roles = new Set(account.roles);
                    if (on) roles.add("news"); else roles.delete("news");
                    if (!roles.size) return setMsg("حداقل یک نقش لازم است");
                    patch(account, { roles: [...roles].join(","), join_public: on ? true : account.join_public });
                  }} />
                </label>
                {account.roles.includes("news") && (
                  <label className="flex items-center justify-between gap-3 text-sm">
                    <span>جوین خودکار کانال‌های عمومی</span>
                    <Switch checked={account.join_public} disabled={busy} onCheckedChange={(on) => patch(account, { join_public: on })} />
                  </label>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" disabled={busy} onClick={() => run(async () => {
                    const { data } = await api.post(`/api/system/telegram-sessions/${account.id}/check`);
                    setMsg(data.authorized ? "اتصال این نشست برقرار است." : "تلگرام این نشست را قبول نکرد.");
                  })}>بررسی</Button>
                  <Button variant="outline" size="sm" disabled={busy} onClick={() => patch(account, { enabled: !account.enabled })}>
                    {account.enabled ? "خاموش کردن" : "روشن کردن"}
                  </Button>
                  <Button variant="destructive" size="sm" disabled={busy} onClick={() => ask("این نشست قطع شود؟", () => run(async () => {
                    await api.post(`/api/system/telegram-sessions/${account.id}/disconnect`);
                  }))}>قطع این نشست</Button>
                </div>
              </div>
            )}
          </div>
        ))}

        {!!accounts.length && canWrite && !step && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={busy} onClick={() => run(async () => {
              const { data } = await api.post("/api/system/telegram-sessions/join-sources");
              setMsg(data.message || "عضویت بررسی شد");
            })}>عضو شدن در منابع خبر فعلی</Button>
          </div>
        )}

        {step === "code" && (
          <div className="grid gap-3">
            <Alert title={status.phone_masked || "کد فرستاده شد"}>{status.delivery || "کد را از تلگرام بگیر."}</Alert>
            <Field label="کد تأیید">
              {codeLength ? (
                <OtpField
                  length={codeLength}
                  value={code}
                  onChange={setCode}
                  onComplete={(value) => run(async () => { await api.post("/api/system/telegram-session/code", { code: value }); setCode(""); })}
                  disabled={busy || !canWrite}
                />
              ) : (
                <Input dir="ltr" inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={code} onChange={(e) => setCode(en(e.target.value))} />
              )}
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button variant="brand" disabled={busy || !canWrite} onClick={() => run(async () => { await api.post("/api/system/telegram-session/code", { code: en(code) }); setCode(""); })}>تأیید کد</Button>
              <Button variant="outline" disabled={busy || !canWrite} onClick={() => run(async () => { await api.post("/api/system/telegram-session/resend"); })}>کد دوباره بیاید</Button>
              <Button variant="outline" disabled={busy || !canWrite} onClick={() => run(async () => { await api.post("/api/system/telegram-session/cancel"); })}>انصراف</Button>
            </div>
          </div>
        )}

        {step === "password" && (
          <div className="grid gap-3">
            <Alert>{status.delivery || "رمز دومرحله‌ای تلگرام را وارد کن. این رمز پنل نیست."}</Alert>
            <Field label="رمز دومرحله‌ای">
              <PasswordInput autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button variant="brand" disabled={busy} onClick={() => run(async () => { await api.post("/api/system/telegram-session/password", { password }); setPassword(""); })}>ورود</Button>
              <Button variant="outline" disabled={busy} onClick={() => run(async () => { await api.post("/api/system/telegram-session/cancel"); })}>انصراف</Button>
            </div>
          </div>
        )}

        {!step && (
          <div className="grid gap-3">
            <p className="text-sm font-medium">{accounts.length ? "افزودن نشست دیگر" : "وصل کردن اولین نشست"}</p>
            <Field label="نام، اختیاری" hint="مثلاً پرمیوم کانال یا جمع‌کننده خبر">
              <Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
            </Field>
            <Field label="کار این اکانت">
              <Select value={form.roles} onChange={(e) => setForm({ ...form, roles: e.target.value })} options={[
                { value: "both", label: "هر دو: ایموجی متحرک و جمع خبر" },
                { value: "emoji", label: "فقط ایموجی متحرک" },
                { value: "news", label: "فقط عضویت و جمع خبر" },
              ]} />
            </Field>
            <Field label="API ID" hint="عدد صفحهٔ my.telegram.org، برای همان اکانت">
              <Input dir="ltr" inputMode="numeric" autoComplete="off" value={form.api_id} onChange={(e) => setForm({ ...form, api_id: e.target.value })} />
            </Field>
            <Field label="API hash">
              <PasswordInput autoComplete="off" value={form.api_hash} onChange={(e) => setForm({ ...form, api_hash: e.target.value })} />
            </Field>
            <Field label="شماره با کد کشور" hint="رقم فارسی قبول است. ۰۹۱۲… و ۹۱۲… هر دو به ‎+98 تبدیل می‌شوند">
              <Input dir="ltr" inputMode="tel" autoComplete="tel" placeholder="+98912…" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            <Button variant="brand" disabled={!canWrite} loading={busy} onClick={() => run(async () => {
              await api.post("/api/system/telegram-session/start", { ...form, api_id: en(form.api_id), phone: en(form.phone) });
            })}>
              فرستادن کد تلگرام
            </Button>
            {!canWrite && <p className="text-xs text-muted-foreground">فقط مالک یا ادمین می‌تواند نشست را وصل کند.</p>}
          </div>
        )}

        {canWrite && (
          <div className="grid gap-2">
            <Field label="عضو شدن در یک کانال عمومی">
              <Input dir="ltr" value={joinName} onChange={(e) => setJoinName(e.target.value)} placeholder="@channel یا https://t.me/+invite" />
            </Field>
            <Button variant="outline" disabled={busy || !joinName.trim()} onClick={() => run(async () => {
              const { data } = await api.post("/api/system/telegram-sessions/join", { username: joinName.trim() });
              setMsg(data.message || "انجام شد");
              setJoinName("");
            })}>جوین و افزودن به منابع خبر</Button>
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          رشتهٔ نشست، API hash، کد و رمز هیچ‌وقت در پاسخ، لاگ یا فایل پشتیبان نمی‌آیند. از ربات هم می‌توانی /sessions و /join @channel را بفرستی. وضعیت کلی در <Link className="underline" to="/health">سلامت</Link> است.
        </p>
      </CardContent>
    </Card>
  );
}
