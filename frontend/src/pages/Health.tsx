import { useEffect, useState } from "react";
import api from "../services/api";
import { Alerts, Badge, Card, Page, Stat } from "../components";

export default function Health() {
  const [data, setData] = useState<any>(null);
  const [msg, setMsg] = useState("");
  async function load() { setData((await api.get("/api/system/health")).data); }
  useEffect(() => { load().catch((e) => setMsg(e.response?.data?.detail || "خطا")); }, []);
  if (!data) return <div className="muted">{msg || "در حال معاینه..."}</div>;
  const webhook = data.webhook || {};
  return (
    <Page kicker="عملیات" title="سلامت و وبهوک" actions={<button className="btn-gold" onClick={async () => { try { const r = await api.post("/api/system/webhook/reset"); setMsg(`وبهوک ثبت شد: ${r.data.url || "ok"}`); load(); } catch (e: any) { setMsg(e.response?.data?.detail || "ثبت وبهوک نشد"); } }}>ثبت دوباره وبهوک</button>}>
      <Alerts items={data.alerts} />
      <div className="grid stats">
        <Stat label="دیتابیس" value={data.external_database ? "Postgres" : "SQLite"} hint={data.database} />
        <Stat label="بات" value={data.bot_info?.username ? `@${data.bot_info.username}` : "قطع"} />
        <Stat label="نسخه" value={data.version} />
        <Stat label="صف وبهوک" value={webhook.pending_update_count ?? "—"} />
        <Stat label="حالت ایموجی" value={data.premium_mode} />
        <Stat label="نشست کاربر" value={data.user_session_configured ? "وصل" : "ندارد"} />
      </div>
      <Card title="وبهوک">
        <div className="tiny">آدرس مورد انتظار: {data.webhook_url || "تنظیم نشده"}</div>
        <div className="tiny">آدرس ثبت‌شده: {webhook.url || "—"}</div>
        {webhook.last_error_message && <div className="alert danger" style={{ marginTop: 10 }}>{webhook.last_error_message}</div>}
        <div className="row" style={{ marginTop: 10 }}>
          <Badge tone={data.database === "connected" ? "ok" : "bad"}>DB</Badge>
          <Badge tone={data.bot === "connected" ? "ok" : "bad"}>Bot</Badge>
          <Badge tone={data.kill_switch ? "bad" : "ok"}>{data.kill_switch ? "Kill" : "زنده"}</Badge>
          <Badge tone={data.dry_run ? "warn" : "ok"}>{data.dry_run ? "Dry" : "ادیت واقعی"}</Badge>
        </div>
        {msg && <div className="tiny">{msg}</div>}
      </Card>
      {!data.user_session_configured && data.premium_mode !== "off" && (
        <div className="alert warn">نشست پرمیوم وصل نیست. نقل‌قول و لینک عضویت اعمال می‌شوند، ولی ایموجی متحرک داخل کانال تا وقتی TG_SESSION_STRING تنظیم نشود به شکل ساده می‌ماند. Bot API این را برای کانال تضمین نمی‌کند.</div>
      )}
      <Card title="چک‌لیست راه‌اندازی">
        <ol className="tiny">
          <li>در Railway یک Postgres بساز و DATABASE_URL را به سرویس ربات وصل کن.</li>
          <li>BOT_TOKEN، ADMIN_SECRET، JWT_SECRET و WEBHOOK_SECRET را بگذار.</li>
          <li>ربات را ادمین کانال کن و تیک Edit messages را روشن کن.</li>
          <li>یک پست آزمایشی بفرست. اگر حالت آزمایشی روشن است، اول از تنظیمات خاموشش کن.</li>
          <li>برای ایموجی متحرک داخل کانال، اگر Bot API رد کرد، نشست پرمیوم را وصل کن.</li>
        </ol>
      </Card>
    </Page>
  );
}
