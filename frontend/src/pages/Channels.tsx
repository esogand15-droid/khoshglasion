import { useEffect, useState } from "react";
import api from "../services/api";

export default function Channels() {
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ chat_id: "", title: "", username: "" });
  const [msg, setMsg] = useState("");

  async function load() { const { data } = await api.get("/api/channels"); setItems(data); }
  useEffect(() => { load(); }, []);

  async function add() {
    if (!form.chat_id) return;
    try {
      await api.post("/api/channels", { chat_id: Number(form.chat_id), title: form.title || undefined, username: form.username || undefined });
      setForm({ chat_id: "", title: "", username: "" });
      setMsg("کانال اضافه شد");
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
      <div className="glass rounded-2xl p-5 flex flex-col gap-4">
        <div className="text-sm font-medium text-white">افزودن کانال</div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input value={form.chat_id} onChange={(e) => setForm({ ...form, chat_id: e.target.value })} placeholder="Chat ID (مثلا -100...)" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30" />
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="عنوان کانال" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30" />
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="یوزرنیم (اختیاری)" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30" />
          <button onClick={add} className="bg-gradient-to-r from-violet-600 to-blue-600 rounded-xl py-2.5 text-sm font-medium text-white">افزودن</button>
        </div>
        {msg && <div className="text-xs text-violet-300">{msg}</div>}
        <p className="text-[11px] text-white/30">برای یافتن Chat ID: ربات را ادمین کانال کنید، یک پست بفرستید و لاگ webhook را ببینید. یا از @userinfobot استفاده کنید.</p>
      </div>
      <div className="glass rounded-2xl p-5 overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-white/40"><tr><th className="text-right py-2">Chat ID</th><th className="text-right py-2">عنوان</th><th className="text-right py-2">فعال</th><th className="text-right py-2">خوشگل‌سازی</th><th className="text-right py-2">ایموجی</th><th className="text-right py-2">عملیات</th></tr></thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-t border-white/5">
                <td className="py-3 font-mono text-white/70">{c.chat_id}</td>
                <td className="py-3 text-white">{c.title || c.username || "-"}</td>
                <td className="py-3"><button onClick={() => toggle(c.id, "enabled", !c.enabled)} className={`rounded-full px-2 py-1 text-[11px] ${c.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-white/50"}`}>{c.enabled ? "فعال" : "غیرفعال"}</button></td>
                <td className="py-3"><button onClick={() => toggle(c.id, "auto_beautify", !c.auto_beautify)} className={`rounded-full px-2 py-1 text-[11px] ${c.auto_beautify ? "bg-blue-500/20 text-blue-300" : "bg-white/10 text-white/50"}`}>{c.auto_beautify ? "روشن" : "خاموش"}</button></td>
                <td className="py-3"><button onClick={() => toggle(c.id, "emoji_replacement", !c.emoji_replacement)} className={`rounded-full px-2 py-1 text-[11px] ${c.emoji_replacement ? "bg-violet-500/20 text-violet-300" : "bg-white/10 text-white/50"}`}>{c.emoji_replacement ? "روشن" : "خاموش"}</button></td>
                <td className="py-3"><button onClick={async () => { if (confirm("حذف کانال؟")) { await api.delete(`/api/channels/${c.id}`); load(); } }} className="text-red-400 hover:text-red-300">حذف</button></td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-white/30">هنوز کانالی ثبت نشده — یکی اضافه کن</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
