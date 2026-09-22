import { useEffect, useState } from "react";
import api from "../services/api";

export default function Styles() {
  const [items, setItems] = useState<any[]>([]);
  async function load() { const { data } = await api.get("/api/styles"); setItems(data); }
  useEffect(() => { load(); }, []);
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-bold text-white">استایل‌ها</h1>
      <p className="text-sm text-white/50">هشت استایل داخلی بر اساس دستهٔ محتوا به‌صورت خودکار انتخاب می‌شود. می‌تونی استایل سفارشی هم بسازی (در API).</p>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {items.map((s) => (
          <div key={s.id} className="glass rounded-2xl p-5 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-violet-400" />
              <span className="text-sm font-medium text-white">{s.name}</span>
              {s.is_builtin && <span className="glass rounded-full px-2 py-0.5 text-[10px] text-white/50">پیش‌فرض</span>}
            </div>
            <div className="text-xs text-white/40 font-mono">{s.slug}</div>
            <div className="text-xs text-white/50 line-clamp-3 whitespace-pre-wrap">{(() => { try { const c = JSON.parse(s.config); return c.footer || c.config || s.config; } catch { return s.config; } })()}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
