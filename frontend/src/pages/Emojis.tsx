import { useEffect, useState } from "react";
import api from "../services/api";
import { Badge, Card, Field, Page } from "../components";

export default function Emojis() {
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "70" });
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");

  async function load() { setItems((await api.get("/api/emojis")).data); }
  useEffect(() => { load().catch(() => {}); }, []);
  const shown = items.filter((item) => !q || `${item.unicode_emoji} ${item.custom_emoji_id} ${item.category || ""}`.includes(q));

  return (
    <Page kicker="کتابخانه متحرک" title="ایموجی پرمیوم" actions={<button className="btn" onClick={async () => { const { data } = await api.get("/api/emojis/export"); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "khoshgelasion-emojis.json"; a.click(); }}>خروجی</button>}>
      <Card title="چطور ID واقعی بگیری؟">
        <p className="tiny">به ربات در خصوصی یک پیام با ایموجی پرمیوم فوروارد کن. همان لحظه <b>custom_emoji_id</b> وارد کتابخانه می‌شود. یا از Saved Messages به @userinfobot فوروارد کن. صاحب ربات باید تلگرام پرمیوم داشته باشد؛ برای کانال، اگر Bot API ایموجی را رد کرد، نشست کاربر را در تنظیمات وصل کن.</p>
      </Card>
      <Card title="نگاشت تازه">
        <div className="grid" style={{ gridTemplateColumns: "120px 1.4fr 1fr 90px auto" }}>
          <Field label="ایموجی"><input value={form.unicode_emoji} onChange={(e) => setForm({ ...form, unicode_emoji: e.target.value })} /></Field>
          <Field label="custom_emoji_id"><input value={form.custom_emoji_id} onChange={(e) => setForm({ ...form, custom_emoji_id: e.target.value })} /></Field>
          <Field label="دسته"><input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></Field>
          <Field label="اولویت"><input value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} /></Field>
          <button className="btn-gold" onClick={async () => {
            try {
              await api.post("/api/emojis", { ...form, priority: Number(form.priority), category: form.category || undefined });
              setForm({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "70" });
              setMsg("اضافه شد");
              load();
            } catch (error: any) { setMsg(error.response?.data?.detail || "ثبت نشد"); }
          }}>افزودن</button>
        </div>
        {msg && <div className="tiny">{msg}</div>}
      </Card>
      <div className="row">
        <input style={{ maxWidth: 280 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجو" />
        <button className="btn" onClick={async () => { const ids = shown.slice(0, 20).map((item) => item.custom_emoji_id); const { data } = await api.post("/api/emojis/validate", { custom_emoji_ids: ids }); setMsg(`معتبر: ${data.valid?.length || 0} / نامعتبر: ${data.invalid?.length || 0}${data.error ? " · " + data.error : ""}`); }}>اعتبارسنجی ۲۰ تای اول</button>
        <button className="btn" onClick={async () => { await api.post("/api/emojis/cleanup-fake"); load(); }}>حذف IDهای فیک</button>
      </div>
      <Card>
        <table>
          <thead><tr><th></th><th>ID</th><th>منبع</th><th>استفاده</th><th>وضعیت</th><th></th></tr></thead>
          <tbody>
            {shown.map((item) => (
              <tr key={item.id}>
                <td style={{ fontSize: 22 }}>{item.unicode_emoji}</td>
                <td className="tiny">{item.custom_emoji_id}{item.custom_emoji_id?.startsWith("53683241") && <Badge tone="warn">فیک</Badge>}</td>
                <td>{item.source || item.category || "—"}</td>
                <td>{item.usage_count || 0}</td>
                <td><Badge tone={item.enabled ? "ok" : "info"}>{item.enabled ? "فعال" : "خاموش"}</Badge></td>
                <td className="row">
                  <button className="btn" onClick={async () => { await api.patch(`/api/emojis/${item.id}`, { enabled: !item.enabled }); load(); }}>{item.enabled ? "خاموش" : "روشن"}</button>
                  <button className="btn-danger" onClick={async () => { await api.delete(`/api/emojis/${item.id}`); load(); }}>حذف</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </Page>
  );
}
