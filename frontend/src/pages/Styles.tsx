import { useEffect, useState } from "react";
import api from "../services/api";
import { Badge, Card, Field, Page } from "../components";

export default function Styles() {
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ name: "", slug: "", footer: "", divider: "━━━━━━━━━━━━" });
  const [msg, setMsg] = useState("");
  async function load() { setItems((await api.get("/api/styles")).data); }
  useEffect(() => { load().catch(() => {}); }, []);

  return (
    <Page kicker="هویت بصری" title="استایل و فوتر">
      <Card title="استایل سفارشی">
        <div className="grid cards-2">
          <Field label="نام"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="شناسه لاتین"><input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="rotbeland" /></Field>
          <Field label="فوتر"><textarea value={form.footer} onChange={(e) => setForm({ ...form, footer: e.target.value })} /></Field>
          <Field label="جداکننده"><input value={form.divider} onChange={(e) => setForm({ ...form, divider: e.target.value })} /></Field>
        </div>
        <button className="btn-gold" onClick={async () => {
          try {
            await api.post("/api/styles", { name: form.name, slug: form.slug, config: { footer: form.footer, divider: form.divider, add_footer: true } });
            setMsg("ساخته شد. در تنظیم کانال انتخابش کن.");
            load();
          } catch (error: any) { setMsg(error.response?.data?.detail || "ساخته نشد"); }
        }}>ساخت استایل</button>
        {msg && <div className="tiny">{msg}</div>}
      </Card>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
        {items.map((style) => {
          let footer = style.config;
          try { footer = JSON.parse(style.config).footer || style.config; } catch { /* keep raw */ }
          return (
            <Card key={style.id} title={style.name} extra={style.is_builtin ? <Badge>داخلی</Badge> : <button className="btn-danger" onClick={async () => { await api.delete(`/api/styles/${style.id}`); load(); }}>حذف</button>}>
              <div className="tiny">{style.slug}</div>
              <div className="preview-paper" style={{ marginTop: 10 }}>{footer || "بدون فوتر"}</div>
            </Card>
          );
        })}
      </div>
    </Page>
  );
}
