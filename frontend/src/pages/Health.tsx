import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Page } from "../components/page";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Stat } from "@/components/ui/stat";
import { fa } from "@/lib/utils";

export default function Health() {
  const [data, setData] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const role = useAuth((state) => state.role);
  const canReset = !role || role === "OWNER" || role === "ADMIN";
  async function load() { setData((await api.get("/api/system/health")).data); }
  useEffect(() => { load().catch((e) => setMsg(e.response?.data?.detail || "خطا")); }, []);
  if (!data) return <Skeleton shimmer className="h-40 rounded-2xl" aria-label={msg || "در حال معاینه"} />;
  const webhook = data.webhook || {};
  return (
    <Page
      kicker="عملیات"
      title="سلامت و وبهوک"
      actions={canReset ? <Button variant="brand" onClick={async () => { try { const r = await api.post("/api/system/webhook/reset"); setMsg(`وبهوک ثبت شد: ${r.data.url || "ok"}`); load(); } catch (e: any) { setMsg(e.response?.data?.detail || "ثبت وبهوک نشد"); } }}>ثبت دوباره وبهوک</Button> : undefined}
    >
      {(data.alerts || []).map((item: any, index: number) => (
        <Alert key={item.code || index} variant={item.level === "danger" ? "destructive" : item.level === "info" ? "info" : "warning"}>
          <span>{item.text}</span>
          {item.fix_path && <Link className="mt-2 block font-medium underline" to={item.fix_path}>{item.fix_label || "رفع در پنل"}</Link>}
        </Alert>
      ))}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Stat label="دیتابیس" value={data.external_database ? "Postgres" : "SQLite"} />
        <Stat label="بات" value={data.bot_info?.username ? `@${data.bot_info.username}` : "قطع"} />
        <Stat label="نسخه" value={data.version || "—"} />
        <Stat label="صف وبهوک" value={webhook.pending_update_count == null ? "—" : fa(webhook.pending_update_count)} />
        <Stat label="حالت ایموجی" value={data.premium_mode} />
        <Stat label="نشست کاربر" value={data.user_session_configured ? (data.user_session_username ? `@${data.user_session_username}` : "وصل") : "ندارد"} />
      </div>
      <Card>
        <CardHeader><CardTitle>وبهوک</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">آدرس مورد انتظار: {data.webhook_url || "تنظیم نشده"}</p>
          <p className="text-xs text-muted-foreground" dir="ltr">آدرس ثبت‌شده: {webhook.url || "—"}</p>
          {webhook.last_error_message && (
            <Alert variant="destructive">
              <span>{webhook.last_error_message}</span>
              <Link className="mt-2 block font-medium underline" to="/settings?tab=problems">ثبت دوباره وبهوک از تنظیمات</Link>
            </Alert>
          )}
          <div className="flex flex-wrap gap-3">
            <Badge variant={data.database === "connected" ? "success" : "destructive"}>DB</Badge>
            <Badge variant={data.bot === "connected" ? "success" : "destructive"}>Bot</Badge>
            <Badge variant={data.kill_switch ? "destructive" : "success"}>{data.kill_switch ? "Kill" : "زنده"}</Badge>
            <Badge variant={data.dry_run ? "warning" : "success"}>{data.dry_run ? "Dry" : "ادیت واقعی"}</Badge>
          </div>
          {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
        </CardContent>
      </Card>
      {!data.user_session_configured && data.premium_mode !== "off" && data.premium_mode !== "bot" && (
        <Alert variant="warning">نشست پرمیوم وصل نیست. بدون نشست، ادیت پرمیوم کانال انجام نمی‌شود و نسخهٔ ایموجی معمولی فرستاده نمی‌شود. از <Link className="underline" to="/settings?tab=session">تنظیمات، تب نشست</Link> با شماره و کد تلگرام وصلش کن.</Alert>
      )}
      <Card>
        <CardHeader><CardTitle>چک‌لیست راه‌اندازی</CardTitle></CardHeader>
        <CardContent>
          <ol className="list-decimal space-y-1 ps-5 text-sm text-muted-foreground">
            <li>دیتابیس پایدار را در میزبان با متغیر DATABASE_URL وصل کن. این یکی را پنل وسط اجرا عوض نمی‌کند.</li>
            <li>توکن، رمز پنل، کلید ورود و رمز وبهوک را از تنظیمات، بخش مشکلات بگذار. لازم نیست روی سرور دستور بزنی.</li>
            <li>ربات را ادمین کانال کن و تیک Edit messages را روشن کن.</li>
            <li>یک پست آزمایشی بفرست. اگر حالت آزمایشی روشن است، اول از تنظیمات خاموشش کن.</li>
            <li>برای ایموجی متحرک داخل کانال، در تنظیمات تب نشست با اکانت پرمیوم وارد شو. صاحب ربات بودن کافی نیست.</li>
          </ol>
        </CardContent>
      </Card>
    </Page>
  );
}
