import { useEffect, useState } from "react";
import api from "../services/api";

export default function Emojis() {
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "50" });
  const [msg, setMsg] = useState("");

  async function load() { const { data } = await api.get("/api/emojis"); setItems(data); }
  useEffect(() => { load(); }, []);

  async function add() {
    if (!form.unicode_emoji || !form.custom_emoji_id) { setMsg("ایموجی و Custom Emoji ID الزامی است"); return; }
    try {
      await api.post("/api/emojis", { unicode_emoji: form.unicode_emoji, custom_emoji_id: form.custom_emoji_id, category: form.category || undefined, priority: Number(form.priority) });
      setForm({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "50" });
      setMsg("اضافه شد");
      load();
    } catch (e: any) { setMsg(e.response?.data?.detail || "خطا"); }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">کتابخانه ایموجی</h1>
        <div className="flex gap-2">
          <button onClick={async () => { const { data } = await api.get("/api/emojis/export"); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "emoji-mapping.json"; a.click(); }} className="glass rounded-xl px-3 py-2 text-xs">خروجی JSON</button>
        </div>
      </div>
      <div className="glass rounded-2xl p-5 flex flex-col gap-4">
        <div className="text-sm font-medium text-white">افزودن نگاشت جدید</div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <input value={form.unicode_emoji} onChange={(e) => setForm({ ...form, unicode_emoji: e.target.value })} placeholder="ایموجی (مثلا 📢)" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30" />
          <input value={form.custom_emoji_id} onChange={(e) => setForm({ ...form, custom_emoji_id: e.target.value })} placeholder="Custom Emoji ID" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30 md:col-span-2" />
          <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="دسته (اختیاری)" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30" />
          <button onClick={add} className="bg-gradient-to-r from-violet-600 to-blue-600 rounded-xl py-2.5 text-sm font-medium text-white">افزودن</button>
        </div>
        {msg && <div className="text-xs text-violet-300">{msg}</div>}
        <p className="text-[11px] text-white/30">برای یافتن Custom Emoji ID: در تلگرام یک custom emoji بفرست، سپس via @userinfobot یا getCustomEmojiStickers را بررسی کن. یا از <code className="glass px-1.5 py-0.5 rounded">getCustomEmojiStickers</code> API استفاده کن.</p>
      </div>
      <div className="glass rounded-2xl p-5 overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-white/40"><tr><th className="text-right py-2">ایموجی</th><th className="text-right py-2">Custom ID</th><th className="text-right py-2">دسته</th><th className="text-right py-2">اولویت</th><th className="text-right py-2">وضعیت</th><th className="text-right py-2">عملیات</th></tr></thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.id} className="border-t border-white/5">
                <td className="py-3 text-lg">{e.unicode_emoji}</td>
                <td className="py-3 font-mono text-[11px] text-white/60 max-w-[180px] truncate">{e.custom_emoji_id}</td>
                <td className="py-3 text-white/60">{e.category || "-"}</td>
                <td className="py-3 text-white/60">{e.priority}</td>
                <td className="py-3"><span className={`rounded-full px-2 py-1 text-[11px] ${e.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-white/50"}`}>{e.enabled ? "فعال" : "غیرفعال"}</span></td>
                <td className="py-3 flex gap-2">
                  <button onClick={async () => { await api.patch(`/api/emojis/${e.id}`, { enabled: !e.enabled }); load(); }} className="text-violet-400 hover:text-violet-300">{e.enabled ? "غیرفعال" : "فعال"}</button>
                  <button onClick={async () => { if (confirm("حذف؟")) { await api.delete(`/api/emojis/${e.id}`); load(); } }} className="text-red-400 hover:text-red-300">حذف</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-white/30">هنوز نگاشتی ثبت نشده</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
