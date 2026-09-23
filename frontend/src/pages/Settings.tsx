import { useEffect, useState } from "react";
import api from "../services/api";
import { Card, Field, Page, Toggle } from "../components";

export default function Settings() {
  const [data, setData] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [aiTest, setAiTest] = useState<any>(null);
  const [testing, setTesting] = useState(false);
  const [password, setPassword] = useState({ current_password: "", new_password: "" });
  const [adminForm, setAdminForm] = useState({ username: "", password: "", role: "ADMIN" });

  async function load() { setData((await api.get("/api/system/settings")).data); }
  useEffect(() => { load().catch(() => {}); }, []);

  async function save(partial: any) {
    setData({ ...data, ...(await api.post("/api/system/settings", partial)).data });
    setMsg("ذخیره شد و بدون ری‌استارت اعمال می‌شود.");
  }
  if (!data) return <div className="muted">در حال بارگذاری تنظیم‌ها...</div>;

  return (
    <Page kicker="کنترل زنده" title="اتاق تنظیم">
      {msg && <div className="alert info">{msg}</div>}
      <div className="grid cards-2">
        <Card title="کلیدهای پردازش">
          <Toggle on={data.dry_run} label="حالت آزمایشی (ادیت واقعی نمی‌شود)" onClick={() => save({ dry_run: !data.dry_run })} />
          <Toggle on={data.kill_switch} label="توقف اضطراری" onClick={() => save({ kill_switch: !data.kill_switch })} />
          <Toggle on={data.auto_register_channels} label="ثبت خودکار کانال وقتی ربات ادمین می‌شود" onClick={() => save({ auto_register_channels: !data.auto_register_channels })} />
          <Toggle on={data.reprocess_edits} label="بازنویسی اگر ادمین بعداً پست را ادیت کرد" onClick={() => save({ reprocess_edits: !data.reprocess_edits })} />
          <Toggle on={data.persian_normalize} label="یکسان‌سازی ی و ک فارسی" onClick={() => save({ persian_normalize: !data.persian_normalize })} />
          <Toggle on={data.preserve_links} label="حفظ لینک، منشن و هشتگ" onClick={() => save({ preserve_links: !data.preserve_links })} />
        </Card>
        <Card title="هوش مصنوعی">
          <Toggle on={data.ai_enabled} label="بازنویسی هوشمند" onClick={() => save({ ai_enabled: !data.ai_enabled })} />
          <div className="grid" style={{ marginTop: 12 }}>
            <Field label="Base URL"><input value={data.ai_base_url || ""} onChange={(e) => setData({ ...data, ai_base_url: e.target.value })} placeholder="https://integrate.api.nvidia.com/v1" /></Field>
            <p className="tiny">برای NVIDIA همین را بگذار: https://integrate.api.nvidia.com/v1 — سیستم خودش /chat/completions را اضافه می‌کند و /v1 را دوباره نمی‌چسباند. درخواست واقعی: {data.ai_endpoint || "بعد از ذخیره دیده می‌شود"} · provider: {data.ai_provider || "—"}</p>
            <Field label="Model"><input value={data.ai_model || ""} onChange={(e) => setData({ ...data, ai_model: e.target.value })} placeholder="openai/gpt-oss-20b" /></Field>
            <Field label={`کلید API ${data.ai_api_key_masked || ""}`}><input type="password" placeholder="خالی = بدون تغییر" onChange={(e) => setData({ ...data, ai_api_key: e.target.value })} /></Field>
            <div className="row">
              <button className="btn-gold" onClick={() => save({ ai_enabled: data.ai_enabled, ai_base_url: data.ai_base_url, ai_model: data.ai_model, ai_api_key: data.ai_api_key || undefined, ai_temperature: Number(data.ai_temperature), ai_max_tokens: Number(data.ai_max_tokens) })}>ذخیره AI</button>
              <button className="btn" disabled={testing} onClick={async () => {
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
              }}>{testing ? "در حال تست..." : "تست اتصال"}</button>
            </div>
            {aiTest && (
              <div className={aiTest.ok ? "alert info" : "alert danger"}>
                <div>{aiTest.ok ? `مدل جواب داد: ${aiTest.sample || "سلام"}` : aiTest.error}</div>
                <div className="tiny">{aiTest.provider} · {aiTest.endpoint}{aiTest.latency_ms ? ` · ${aiTest.latency_ms}ms` : ""}</div>
              </div>
            )}
          </div>
        </Card>
      </div>
      <Card title="ایموجی، اعلان، فوتر پیش‌فرض">
        <div className="grid cards-2">
          <Field label="حالت ایموجی">
            <select value={data.premium_mode} onChange={(e) => save({ premium_mode: e.target.value })}>
              <option value="auto">خودکار: نشست کاربر، بعد Bot API، بعد متن ساده</option>
              <option value="bot">فقط Bot API</option>
              <option value="user">فقط نشست پرمیوم</option>
              <option value="off">بدون ایموجی پرمیوم</option>
            </select>
          </Field>
          <Field label="سقف ایموجی در هر پست"><input type="number" value={data.max_emoji_per_post} onChange={(e) => setData({ ...data, max_emoji_per_post: e.target.value })} onBlur={() => save({ max_emoji_per_post: Number(data.max_emoji_per_post) })} /></Field>
          <Field label="تأخیر ادیت (ثانیه)"><input type="number" value={data.edit_delay_seconds} onChange={(e) => setData({ ...data, edit_delay_seconds: e.target.value })} onBlur={() => save({ edit_delay_seconds: Number(data.edit_delay_seconds) })} /></Field>
          <Field label="آیدی ادمین‌های تلگرام"><input value={data.admin_telegram_ids || ""} onChange={(e) => setData({ ...data, admin_telegram_ids: e.target.value })} onBlur={() => save({ admin_telegram_ids: data.admin_telegram_ids })} placeholder="123,456" /></Field>
          <Field label="چت اعلان خطا"><input value={data.notify_chat_id || ""} onChange={(e) => setData({ ...data, notify_chat_id: e.target.value })} onBlur={() => save({ notify_chat_id: data.notify_chat_id })} /></Field>
          <Field label="فوتر پیش‌فرض سراسری"><textarea value={data.default_footer || ""} onChange={(e) => setData({ ...data, default_footer: e.target.value })} onBlur={() => save({ default_footer: data.default_footer })} /></Field>
          <Field label="لینک عضویت"><input value={data.footer_url || ""} onChange={(e) => setData({ ...data, footer_url: e.target.value })} onBlur={() => save({ footer_url: data.footer_url })} placeholder="https://t.me/Rotbeland1" /></Field>
          <Field label="یوزرنیم پشتیبانی"><input value={data.support_username || ""} onChange={(e) => setData({ ...data, support_username: e.target.value })} onBlur={() => save({ support_username: data.support_username })} placeholder="Rotbeland_support" /></Field>
        </div>
        <p className="tiny">نشست کاربر از محیط TG_SESSION_STRING خوانده می‌شود و در پنل ذخیره نمی‌شود. وضعیت: {data.user_session_configured ? "تنظیم شده" : "تنظیم نشده"}.</p>
      </Card>
      <div className="grid cards-2">
        <Card title="رمز پنل">
          <div className="grid">
            <Field label="رمز فعلی"><input type="password" autoComplete="current-password" value={password.current_password} onChange={(e) => setPassword({ ...password, current_password: e.target.value })} /></Field>
            <Field label="رمز جدید، حداقل ۸ کاراکتر"><input type="password" autoComplete="new-password" value={password.new_password} onChange={(e) => setPassword({ ...password, new_password: e.target.value })} /></Field>
            <button className="btn" onClick={async () => { try { await api.post("/api/auth/password", password); setMsg("رمز عوض شد"); } catch (e: any) { setMsg(e.response?.data?.detail || "عوض نشد"); } }}>تغییر رمز</button>
          </div>
        </Card>
        <Card title="ادمین تازه و پشتیبان">
          <div className="grid">
            <Field label="نام کاربری ادمین تازه"><input autoComplete="off" value={adminForm.username} onChange={(e) => setAdminForm({ ...adminForm, username: e.target.value })} /></Field>
            <Field label="رمز ادمین تازه"><input type="password" autoComplete="new-password" value={adminForm.password} onChange={(e) => setAdminForm({ ...adminForm, password: e.target.value })} /></Field>
            <button className="btn" onClick={async () => { try { await api.post("/api/system/admins", adminForm); setMsg("ادمین ساخته شد"); } catch (e: any) { setMsg(e.response?.data?.detail || "ساخته نشد"); } }}>ساخت ادمین</button>
            <div className="row">
              <button className="btn" onClick={async () => { const { data } = await api.get("/api/system/backup"); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "khoshgelasion-backup.json"; a.click(); }}>دانلود پشتیبان</button>
              <label className="btn">بازیابی<input type="file" hidden accept="application/json" onChange={async (e) => { const file = e.target.files?.[0]; if (!file) return; const payload = JSON.parse(await file.text()); const { data } = await api.post("/api/system/restore", payload); setMsg(`بازیابی شد: ${JSON.stringify(data.restored)}`); load(); }} /></label>
            </div>
          </div>
        </Card>
      </div>
    </Page>
  );
}
