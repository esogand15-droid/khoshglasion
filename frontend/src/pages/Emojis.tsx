import { useEffect, useState } from "react";
import api from "../services/api";

const PACKS = [
  { name: "اطلاعیه و خبر فوری", icon: "📢", emojis: ["📢","📣","🔔","🔥","⚡","📌"], category: "announcement" },
  { name: "منابع و کتاب", icon: "📚", emojis: ["📚","📝","🎓","💡","🔶"], category: "resource" },
  { name: "انگیزشی و موفقیت", icon: "⭐", emojis: ["⭐","🌟","✨","💪","🚀","🏆","👑","❤️"], category: "motivational" },
  { name: "برنامه‌ریزی و آزمون", icon: "🎯", emojis: ["🎯","📅","⏰","📈","💯"], category: "planning" },
  { name: "تخفیف و پیشنهاد", icon: "💎", emojis: ["💎","🎁","🎉"], category: "discount" },
];

export default function Emojis() {
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "50" });
  const [msg, setMsg] = useState("");
  const [search, setSearch] = useState("");
  const [validating, setValidating] = useState<string | null>(null);

  async function load() { const { data } = await api.get("/api/emojis"); setItems(data); }
  useEffect(() => { load(); }, []);

  async function add() {
    if (!form.unicode_emoji || !form.custom_emoji_id) { setMsg("ایموجی و Custom Emoji ID الزامی است"); return; }
    if (!/^\d{10,25}$/.test(form.custom_emoji_id.trim())) { setMsg("Custom Emoji ID باید عدد ۱۰ تا ۲۵ رقمی باشد (مثال: 5310129635848103696)"); return; }
    try {
      await api.post("/api/emojis", { unicode_emoji: form.unicode_emoji, custom_emoji_id: form.custom_emoji_id.trim(), category: form.category || undefined, priority: Number(form.priority) });
      setForm({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "50" });
      setMsg("✅ اضافه شد — برای تست، پیش‌نمایش زنده را باز کن");
      load();
    } catch (e: any) { setMsg(e.response?.data?.detail || "خطا"); }
  }

  async function validateOne(id: string, unicode: string) {
    setValidating(id);
    try {
      const { data } = await api.post("/api/emojis/validate", { custom_emoji_ids: [id] });
      if (data.valid?.includes(id) || data.found?.includes(id)) setMsg(`✅ ${unicode} معتبر است`);
      else setMsg(`⚠️ ${unicode} یافت نشد — ID را چک کن (ممکن است فیک باشد)`);
    } catch { setMsg("⚠️ اعتبارسنجی فعلا در دسترس نیست — ID را دستی در تلگرام تست کن"); }
    finally { setValidating(null); }
  }

  const filtered = search ? items.filter(e => e.unicode_emoji.includes(search) || e.category?.includes(search) || e.custom_emoji_id.includes(search)) : items;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">کتابخانه ایموجی پرمیوم ✨</h1>
          <p className="text-xs text-white/40 mt-1">{items.length} نگاشت فعال • ایموجی‌های پرمیوم متحرک با custom_emoji_id</p>
        </div>
        <div className="flex gap-2">
          <button onClick={async () => { const { data } = await api.get("/api/emojis/export"); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "emoji-mapping.json"; a.click(); }} className="glass rounded-xl px-3 py-2 text-xs">📥 خروجی JSON</button>
          <button onClick={() => { if(confirm("تمام نگاشت‌های فیک (53683241...) حذف شوند؟")) api.post("/api/emojis/cleanup-fake").then(()=>load()); }} className="glass rounded-xl px-3 py-2 text-xs text-amber-300">🧹 حذف فیک‌ها</button>
        </div>
      </div>

      {/* Packs overview */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {PACKS.map(p => (
          <div key={p.name} className="glass rounded-2xl p-4 flex flex-col gap-2">
            <div className="text-lg">{p.icon}</div>
            <div className="text-xs font-medium text-white">{p.name}</div>
            <div className="text-[11px] text-white/30">{p.emojis.length} ایموجی • {p.category}</div>
            <div className="flex flex-wrap gap-1 mt-1">{p.emojis.map(e => <span key={e} className="text-base">{e}</span>)}</div>
          </div>
        ))}
      </div>

      {/* Add form */}
      <div className="glass rounded-2xl p-5 flex flex-col gap-4">
        <div className="text-sm font-medium text-white flex items-center gap-2">افزودن نگاشت پرمیوم <span className="glass rounded-full px-2 py-0.5 text-[10px] text-violet-300">ID واقعی بذار</span></div>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <input value={form.unicode_emoji} onChange={(e) => setForm({ ...form, unicode_emoji: e.target.value })} placeholder="ایموجی (مثلا 📢)" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30" />
          <input value={form.custom_emoji_id} onChange={(e) => setForm({ ...form, custom_emoji_id: e.target.value })} placeholder="Custom Emoji ID (19 رقم)" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30 md:col-span-2 font-mono text-xs" />
          <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="دسته" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none placeholder:text-white/30" />
          <input value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} placeholder="اولویت" type="number" className="glass rounded-xl px-3 py-2.5 text-sm bg-transparent outline-none" />
          <button onClick={add} className="bg-gradient-to-r from-violet-600 to-blue-600 rounded-xl py-2.5 text-sm font-medium text-white">افزودن ✨</button>
        </div>
        {msg && <div className="text-xs text-violet-300 bg-violet-500/10 rounded-xl px-3 py-2">{msg}</div>}
        <div className="glass rounded-xl p-3 text-[11px] text-white/40 leading-5">
          <span className="text-white/70 font-medium">چطور ID واقعی بگیری؟</span> تلگرام → Saved Messages → یه ایموجی پرمیوم بفرست → فوروارد به <code className="glass px-1.5 py-0.5 rounded">@userinfobot</code> → عدد <code className="glass px-1.5 py-0.5 rounded">custom_emoji_id</code> را کپی کن. هر ID باید ۱۹ رقم (543...) باشد — ID های <code className="glass px-1.5 py-0.5 rounded">53683241...</code> فیک sequential هستند و کار نمی‌کنند.
        </div>
      </div>

      {/* Search + list */}
      <div className="glass rounded-2xl p-5 flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="جستجو ایموجی / دسته / ID..." className="glass rounded-xl px-3 py-2 text-xs bg-transparent outline-none placeholder:text-white/30 flex-1" />
          <span className="text-xs text-white/30">{filtered.length} / {items.length}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/40"><tr><th className="text-right py-2">ایموجی</th><th className="text-right py-2">Custom ID</th><th className="text-right py-2">دسته</th><th className="text-right py-2">اولویت</th><th className="text-right py-2">وضعیت</th><th className="text-right py-2">تست</th><th className="text-right py-2">عملیات</th></tr></thead>
            <tbody>
              {filtered.map((e) => {
                const isFake = e.custom_emoji_id?.startsWith("53683241");
                return (
                  <tr key={e.id} className={`border-t border-white/5 ${isFake ? "bg-amber-500/5" : ""}`}>
                    <td className="py-3 text-lg">{e.unicode_emoji}</td>
                    <td className="py-3 font-mono text-[11px] max-w-[180px] truncate"><span className={isFake ? "text-amber-300" : "text-white/60"}>{e.custom_emoji_id}</span>{isFake && <span className="mr-1 text-[10px] bg-amber-500/20 text-amber-300 rounded-full px-1.5 py-0.5">فیک</span>}</td>
                    <td className="py-3 text-white/60">{e.category || "-"}</td>
                    <td className="py-3 text-white/60">{e.priority}</td>
                    <td className="py-3"><span className={`rounded-full px-2 py-1 text-[11px] ${e.enabled ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-white/50"}`}>{e.enabled ? "فعال" : "غیرفعال"}</span></td>
                    <td className="py-3"><button onClick={()=>validateOne(e.custom_emoji_id, e.unicode_emoji)} disabled={!!validating} className="text-violet-400 hover:text-violet-300 text-[11px] disabled:opacity-50">{validating===e.custom_emoji_id ? "..." : "اعتبارسنجی"}</button></td>
                    <td className="py-3 flex gap-2">
                      <button onClick={async () => { await api.patch(`/api/emojis/${e.id}`, { enabled: !e.enabled }); load(); }} className="text-violet-400 hover:text-violet-300">{e.enabled ? "غیرفعال" : "فعال"}</button>
                      <button onClick={async () => { if (confirm("حذف؟")) { await api.delete(`/api/emojis/${e.id}`); load(); } }} className="text-red-400 hover:text-red-300">حذف</button>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && <tr><td colSpan={7} className="py-8 text-center text-white/30">{search ? "نتیجه‌ای یافت نشد" : "هنوز نگاشتی ثبت نشده — از بالا اضافه کن"}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
