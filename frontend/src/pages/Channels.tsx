import { useEffect, useState } from "react";
import api from "../services/api";

export default function Channels() {
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ chat_id: "", title: "", username: "" });
  const [msg, setMsg] = useState("");

  async function load() { const { data } = await api.get("/api/channels"); setItems(data); }
  useEffect(() => { load(); }, []);

  async function add() {
    const cid = Number(form.chat_id);
    if (!form.chat_id || Number.isNaN(cid)) { setMsg("Chat ID عددی بذار — مثلا -1004377389661"); return; }
    try {
      await api.post("/api/channels", { chat_id: cid, title: form.title || undefined, username: form.username || undefined });
      setForm({ chat_id: "", title: "", username: "" });
      setMsg("✅ کانال اضافه شد — حالا ربات را ادمین کن با دسترسی Edit messages");
      load();
    } catch (e: any) { setMsg(e.response?.data?.detail || "خطا"); }
  }
  async function toggle(id: string, field: string, value: any) {
    await api.patch(`/api/channels/${id}`, { [field]: value });
    load();
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-bold text-white">کانال‌ها</h1>
      {/* Add form */}
      <div className="glass rounded-2xl p-5 flex flex-col gap-4">
        <div className="text-sm font-medium text-white">افزودن کانال</div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input value={form.chat_id} onChange={(e) => setForm({ ...form, chat_id: e.target.value })} placeholder="Chat ID (مثلا -1004377389661)" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30 font-mono" />
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="عنوان کانال" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30" />
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="یوزرنیم (اختیاری)" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30" />
          <button onClick={add} className="bg-gradient-to-r from-violet-600 to-blue-600 rounded-xl py-2.5 text-sm font-medium text-white">افزودن</button>
        </div>
        {msg && <div className={`text-xs rounded-xl px-3 py-2 ${msg.startsWith("✅") ? "text-emerald-300 bg-emerald-500/10" : "text-violet-300 bg-violet-500/10"}`}>{msg}</div>}
        <div className="glass rounded-xl p-3 text-[11px] text-white/40 leading-5">
          <b className="text-white/70">چطور Chat ID پیدا کنم؟</b> ربات را ادمین کانال کن → یک پست بفرست → همین صفحه چند ثانیه بعد یک ردیف اسکیپ با <code className="glass px-1 py-0.5 rounded">unknown_channel</code> می‌سازد و Chat ID را نشان می‌دهد، یا از <code className="glass px-1 py-0.5 rounded">@userinfobot</code> / Forward به ربات لاگ استفاده کن. Chat ID همیشه منفی و با <code className="glass px-1 py-0.5 rounded">-100</code> شروع می‌شود.
          <br />
          <b className="text-emerald-300">چک‌لیست بعد از افزودن:</b> ۱) ربات ادمین با Edit messages ۲) همه تیک‌های زیر روشن ۳) DRY_RUN=false برای ادیت واقعی
        </div>
      </div>
      {/* Table */}
      <div className="glass rounded-2xl p-5 overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-white/40"><tr><th className="text-right py-2">Chat ID</th><th className="text-right py-2">عنوان</th><th className="text-right py-2">فعال</th><th className="text-right py-2">خوشگل‌سازی</th><th className="text-right py-2">ایموجی</th><th className="text-right py-2">عملیات</th></tr></thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-t border-white/5">
                <td className="py-3 font-mono text-white/70">{c.chat_id}</td>
                <td className="py-3 text-white">{c.title || c.username || "-"}</td>
                <td className="py-3"><button onClick={() => toggle(c.id, "enabled", !c.enabled)} className={`rounded-full px-2 py-1 text-[11px] ${c.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/20 text-red-300"}`}>{c.enabled ? "فعال" : "غیرفعال"}</button></td>
                <td className="py-3"><button onClick={() => toggle(c.id, "auto_beautify", !c.auto_beautify)} className={`rounded-full px-2 py-1 text-[11px] ${c.auto_beautify ? "bg-blue-500/20 text-blue-300" : "bg-white/10 text-white/50"}`}>{c.auto_beautify ? "روشن" : "خاموش"}</button></td>
                <td className="py-3"><button onClick={() => toggle(c.id, "emoji_replacement", !c.emoji_replacement)} className={`rounded-full px-2 py-1 text-[11px] ${c.emoji_replacement ? "bg-violet-500/20 text-violet-300" : "bg-white/10 text-white/50"}`}>{c.emoji_replacement ? "روشن" : "خاموش"}</button></td>
                <td className="py-3"><button onClick={async () => { if (confirm("حذف کانال؟")) { await api.delete(`/api/channels/${c.id}`); load(); } }} className="text-red-400 hover:text-red-300">حذف</button></td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-white/30">هنوز کانالی ثبت نشده — یکی اضافه کن</td></tr>}
          </tbody>
        </table>
      </div>
      {/* Recent skips */}
      <div className="glass rounded-2xl p-5">
        <div className="text-sm font-medium text-white mb-2">عیب‌یابی سریع</div>
        <p className="text-xs text-white/40">اگر پیام جدید می‌فرستی و ادیت نمی‌شود، برو <b className="text-white/70">پیام‌ها → رد شده</b> و دلیل را ببین. رایج‌ترین‌ها: <code className="glass px-1 py-0.5 rounded text-[11px]">unknown_channel</code> یعنی Chat ID اشتباه، <code className="glass px-1 py-0.5 rounded text-[11px]">no_change</code> یعنی فوتر از قبل هست.</p>
      </div>
    </div>
  );
}
