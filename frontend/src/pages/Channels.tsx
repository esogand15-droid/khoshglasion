import { useEffect, useState } from "react";
import api from "../services/api";
import { Badge, Card, Field, Modal, Page } from "../components";

const EMPTY = { chat_id: "", title: "", username: "" };

export default function Channels() {
  const [items, setItems] = useState<any[]>([]);
  const [styles, setStyles] = useState<any[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [msg, setMsg] = useState("");
  const [edit, setEdit] = useState<any>(null);

  async function load() {
    const [channels, styleRows] = await Promise.all([api.get("/api/channels"), api.get("/api/styles")]);
    setItems(channels.data);
    setStyles(styleRows.data);
  }
  useEffect(() => { load().catch(() => {}); }, []);

  async function add() {
    const chatId = Number(form.chat_id);
    if (!form.chat_id || Number.isNaN(chatId)) { setMsg("Chat ID عددی است، مثل ‎-100…"); return; }
    try {
      await api.post("/api/channels", { chat_id: chatId, title: form.title || undefined, username: form.username || undefined });
      setForm(EMPTY);
      setMsg("کانال ثبت شد. ربات باید ادمین با دسترسی Edit messages باشد.");
      load();
    } catch (error: any) { setMsg(error.response?.data?.detail || "ثبت نشد"); }
  }

  async function save() {
    await api.patch(`/api/channels/${edit.id}`, {
      title: edit.title, username: edit.username, footer_text: edit.footer_text,
      style_id: edit.style_id || null, notes: edit.notes, skip_keywords: edit.skip_keywords,
      signature_text: edit.signature_text, signature_url: edit.signature_url,
      min_chars: Number(edit.min_chars || 1), edit_delay_seconds: edit.edit_delay_seconds === "" ? null : Number(edit.edit_delay_seconds),
      enabled: edit.enabled, auto_beautify: edit.auto_beautify, emoji_replacement: edit.emoji_replacement,
      header_enabled: edit.header_enabled, preserve_buttons: edit.preserve_buttons,
      ai_rewrite: edit.ai_rewrite === "" ? null : edit.ai_rewrite,
    });
    setEdit(null);
    load();
  }

  return (
    <Page kicker="پوشش کانال" title="کانال‌ها" actions={<button className="btn" onClick={() => load()}>تازه‌سازی</button>}>
      <Card title="افزودن یا همگام‌سازی">
        <div className="grid" style={{ gridTemplateColumns: "1.2fr 1fr 1fr auto auto", alignItems: "end" }}>
          <Field label="Chat ID"><input value={form.chat_id} onChange={(e) => setForm({ ...form, chat_id: e.target.value })} placeholder="-100…" /></Field>
          <Field label="عنوان"><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="یوزرنیم"><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></Field>
          <button className="btn-gold" onClick={add}>افزودن</button>
          <button className="btn" onClick={async () => { if (!form.chat_id) return; await api.post("/api/channels/sync", { chat_id: Number(form.chat_id) }); load(); }}>خواندن از تلگرام</button>
        </div>
        {msg && <div className="tiny" style={{ marginTop: 10 }}>{msg}</div>}
        <p className="tiny">اگر ربات را ادمین کانال کنی، کانال خودش ثبت می‌شود. Chat ID کانال منفی است و با ‎-100 شروع می‌شود.</p>
      </Card>
      <Card>
        <div className="table-wrap">
          <table>
            <thead><tr><th>کانال</th><th>Chat ID</th><th>ادیت‌ها</th><th>وضعیت</th><th></th></tr></thead>
            <tbody>
              {items.map((channel) => (
                <tr key={channel.id}>
                  <td><b>{channel.title || "بدون عنوان"}</b><div className="tiny">{channel.username || channel.notes || ""}</div></td>
                  <td className="muted">{channel.chat_id}</td>
                  <td>{channel.posts_edited || 0}</td>
                  <td><Badge tone={channel.enabled && channel.can_edit ? "ok" : "bad"}>{channel.can_edit ? (channel.enabled ? "فعال" : "خاموش") : "بدون دسترسی ادیت"}</Badge></td>
                  <td className="row">
                    <button className="btn" onClick={() => setEdit({ ...channel, ai_rewrite: channel.ai_rewrite ?? "" })}>تنظیم</button>
                    <button className="btn-danger" onClick={async () => { if (confirm("کانال حذف شود؟")) { await api.delete(`/api/channels/${channel.id}`); load(); } }}>حذف</button>
                  </td>
                </tr>
              ))}
              {!items.length && <tr><td colSpan={5} className="tiny">هنوز کانالی نیست.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
      {edit && (
        <Modal title={edit.title || "تنظیم کانال"} onClose={() => setEdit(null)}>
          <div className="grid cards-2">
            <Field label="عنوان"><input value={edit.title || ""} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
            <Field label="استایل"><select value={edit.style_id || ""} onChange={(e) => setEdit({ ...edit, style_id: e.target.value })}><option value="">خودکار بر اساس محتوا</option>{styles.map((s) => <option key={s.id} value={s.slug}>{s.name}</option>)}</select></Field>
            <Field label="فوتر اختصاصی"><textarea value={edit.footer_text || ""} onChange={(e) => setEdit({ ...edit, footer_text: e.target.value })} /></Field>
            <Field label="کلمات ممنوع، با ویرگول"><textarea value={edit.skip_keywords || ""} onChange={(e) => setEdit({ ...edit, skip_keywords: e.target.value })} /></Field>
            <Field label="متن دکمه"><input value={edit.signature_text || ""} onChange={(e) => setEdit({ ...edit, signature_text: e.target.value })} /></Field>
            <Field label="لینک دکمه"><input value={edit.signature_url || ""} onChange={(e) => setEdit({ ...edit, signature_url: e.target.value })} /></Field>
            <Field label="حداقل کاراکتر"><input type="number" value={edit.min_chars || 1} onChange={(e) => setEdit({ ...edit, min_chars: e.target.value })} /></Field>
            <Field label="تأخیر ادیت (ثانیه، خالی = سراسری)"><input value={edit.edit_delay_seconds ?? ""} onChange={(e) => setEdit({ ...edit, edit_delay_seconds: e.target.value })} /></Field>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn" onClick={() => setEdit({ ...edit, enabled: !edit.enabled })}>{edit.enabled ? "فعال" : "خاموش"}</button>
            <button className="btn" onClick={() => setEdit({ ...edit, auto_beautify: !edit.auto_beautify })}>خوشگل‌سازی: {edit.auto_beautify ? "روشن" : "خاموش"}</button>
            <button className="btn" onClick={() => setEdit({ ...edit, emoji_replacement: !edit.emoji_replacement })}>ایموجی: {edit.emoji_replacement ? "روشن" : "خاموش"}</button>
            <button className="btn" onClick={() => setEdit({ ...edit, preserve_buttons: !edit.preserve_buttons })}>دکمه‌ها: {edit.preserve_buttons ? "حفظ" : "حذف"}</button>
            <button className="btn" onClick={() => setEdit({ ...edit, ai_rewrite: edit.ai_rewrite === true ? false : edit.ai_rewrite === false ? "" : true })}>AI: {edit.ai_rewrite === "" ? "سراسری" : edit.ai_rewrite ? "اجباری" : "خاموش"}</button>
          </div>
          <button className="btn-gold" style={{ marginTop: 16 }} onClick={save}>ذخیره کانال</button>
        </Modal>
      )}
    </Page>
  );
}
