import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { OtpField } from "@/components/ui/otp-field";
import { PasswordInput } from "@/components/ui/password-input";
import { Spinner } from "@/components/ui/spinner";
import { en } from "@/lib/utils";

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
  const [form, setForm] = useState({ api_id: "", api_hash: "", phone: "" });
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [live, setLive] = useState<"ok" | "bad" | null>(null);
  const [busy, setBusy] = useState(false);

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

  if (!status) return <Spinner label="در حال خواندن نشست" />;
  const step = status.pending_step;
  const modeBlocks = premiumMode === "bot" || premiumMode === "off";
  const codeLength = status.code_length && status.code_length >= 4 && status.code_length <= 8 ? status.code_length : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>نشست پرمیوم کانال</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          خط طلایی داخل کانال با Bot API ساخته نمی‌شود، حتی اگر صاحب ربات پرمیوم باشد. این‌جا با شمارهٔ همان اکانت پرمیوم وارد شو. API ID و API hash را از my.telegram.org برای همان اکانت بگیر، نه از BotFather.
        </p>
        {modeBlocks && (
          <Alert variant="warning" title="حالت ایموجی این نشست را استفاده نمی‌کند">
            الان روی {premiumMode === "off" ? "بدون ایموجی" : "فقط Bot API"} است. برای خط طلایی، در تب ظاهر پست حالت را بگذار روی خودکار یا فقط نشست پرمیوم.
          </Alert>
        )}
        {msg && <Alert variant="destructive">{msg}</Alert>}

        {status.configured && !step && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant="success">وصل است</Badge>
              {status.premium === true && <Badge variant="brand">پرمیوم</Badge>}
              {status.premium === false && <Badge variant="warning">بدون پرمیوم</Badge>}
              {status.username && <span dir="ltr" className="text-sm">@{status.username}</span>}
              {status.user_id && <span dir="ltr" className="text-xs text-muted-foreground">{status.user_id}</span>}
            </div>
            {status.premium === false && (
              <Alert variant="warning">این اکانت پرمیوم نیست. تلگرام خط طلایی را با اکانت معمولی داخل کانال نشان نمی‌دهد.</Alert>
            )}
            <Alert>
              اکانت باید ادمین کانال باشد و تیک ویرایش پیام داشته باشد. بعد از وصل شدن، خط طلایی را از همین اکانت به ربات فوروارد کن تا شناسهٔ ایموجی ذخیره شود. بذر پیش‌فرض این خط را ندارد.
            </Alert>
            {live === "ok" && <Alert variant="success">اتصال زنده برقرار است. این اکانت برای ادیت کانال استفاده می‌شود.</Alert>}
            {live === "bad" && (
              <Alert variant="warning">رشته ذخیره شده، ولی تلگرام این نشست را قبول نکرد. دوباره وارد شو.</Alert>
            )}
            {canWrite && (
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" disabled={busy} onClick={() => run(async () => {
                  const { data } = await api.post("/api/system/telegram-session/check");
                  setLive(data.authorized ? "ok" : "bad");
                })}>
                  بررسی اتصال
                </Button>
                <Button variant="destructive" disabled={busy} onClick={() => run(async () => { await api.post("/api/system/telegram-session/disconnect"); })}>
                  قطع نشست
                </Button>
              </div>
            )}
          </div>
        )}

        {!status.configured && !step && (
          <div className="grid gap-3">
            <Field label="API ID" hint="عدد صفحهٔ my.telegram.org">
              <Input dir="ltr" inputMode="numeric" autoComplete="off" value={form.api_id} onChange={(e) => setForm({ ...form, api_id: e.target.value })} />
            </Field>
            <Field label="API hash">
              <PasswordInput autoComplete="off" value={form.api_hash} onChange={(e) => setForm({ ...form, api_hash: e.target.value })} />
            </Field>
            <Field label="شماره با کد کشور" hint="رقم فارسی قبول است. ۰۹۱۲… و ۹۱۲… هر دو به ‎+98 تبدیل می‌شوند">
              <Input dir="ltr" inputMode="tel" autoComplete="tel" placeholder="+98912…" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            <Button variant="brand" disabled={busy || !canWrite} onClick={() => run(async () => { await api.post("/api/system/telegram-session/start", { ...form, api_id: en(form.api_id), phone: en(form.phone) }); })}>
              {busy ? <Spinner size="sm" label="در حال فرستادن کد" /> : "فرستادن کد تلگرام"}
            </Button>
            {!canWrite && <p className="text-xs text-muted-foreground">فقط مالک یا ادمین می‌تواند نشست را وصل کند.</p>}
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
                <Input
                  dir="ltr"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={8}
                  value={code}
                  onChange={(e) => setCode(en(e.target.value))}
                />
              )}
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button variant="brand" disabled={busy || !canWrite} onClick={() => run(async () => { await api.post("/api/system/telegram-session/code", { code: en(code) }); setCode(""); })}>
                تأیید کد
              </Button>
              <Button variant="outline" disabled={busy || !canWrite} onClick={() => run(async () => { await api.post("/api/system/telegram-session/resend"); })}>
                کد دوباره بیاید
              </Button>
              <Button variant="outline" disabled={busy || !canWrite} onClick={() => run(async () => { await api.post("/api/system/telegram-session/cancel"); })}>
                انصراف
              </Button>
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
              <Button variant="brand" disabled={busy} onClick={() => run(async () => { await api.post("/api/system/telegram-session/password", { password }); setPassword(""); })}>
                ورود
              </Button>
              <Button variant="outline" disabled={busy} onClick={() => run(async () => { await api.post("/api/system/telegram-session/cancel"); })}>
                انصراف
              </Button>
            </div>
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          رشتهٔ نشست، API hash، کد و رمز هیچ‌وقت در پاسخ، لاگ یا فایل پشتیبان نمی‌آیند. اگر هنوز وصل نیست، از <Link className="underline" to="/health">سلامت</Link> وضعیت را ببین.
        </p>
      </CardContent>
    </Card>
  );
}
