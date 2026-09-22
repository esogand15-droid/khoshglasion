import { useEffect, useState } from "react";
import api from "../services/api";

export default function Messages() {
  const [items, setItems] = useState<any[]>([]);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<any>(null);

  async function load() {
    const { data } = await api.get("/api/messages", { params: { status: status || undefined, limit: 50 } });
    setItems(data);
  }
  useEffect(() => { load(); }, [status]);
  async function open(id: string) {
    const { data } = await api.get(`/api/messages/${id}`);
    setSelected(data);
  }
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">پیام‌ها</h1>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="glass rounded-xl px-3 py-2 text-sm bg-transparent outline-none">
          <option value="" className="bg-[#0a0e1a]">همه وضعیت‌ها</option>
          <option value="edited" className="bg-[#0a0e1a]">ادیت شده</option>
          <option value="skipped" className="bg-[#0a0e1a]">رد شده</option>
          <option value="failed" className="bg-[#0a0e1a]">ناموفق</option>
          <option value="dry_run" className="bg-[#0a0e1a]">Dry Run</option>
        </select>
      </div>
      <div className="glass rounded-2xl p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/40 bg-white/[0.02]"><tr><th className="text-right py-3 px-3">Msg ID</th><th className="text-right py-3">نوع</th><th className="text-right py-3">دسته</th><th className="text-right py-3">وضعیت</th><th className="text-right py-3">زمان</th><th className="text-right py-3">جزئیات</th></tr></thead>
            <tbody>
              {items.map((m) => (
                <tr key={m.id} className="border-t border-white/5 hover:bg-white/[0.02]">
                  <td className="py-3 px-3 font-mono text-white/70">{m.message_id}</td>
                  <td className="py-3 text-white/60">{m.message_type || "-"}</td>
                  <td className="py-3"><span className="glass rounded-full px-2 py-1 text-[11px]">{m.category || "-"}</span></td>
                  <td className="py-3"><span className={`rounded-full px-2 py-1 text-[11px] ${m.status === "edited" ? "bg-emerald-500/20 text-emerald-300" : m.status === "failed" ? "bg-red-500/20 text-red-300" : "bg-white/10 text-white/60"}`}>{m.status}</span></td>
                  <td className="py-3 text-white/40 text-[11px]">{m.created_at ? new Date(m.created_at).toLocaleString("fa-IR") : "-"}</td>
                  <td className="py-3"><button onClick={() => open(m.id)} className="text-violet-400 hover:text-violet-300">نمایش</button></td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={6} className="py-10 text-center text-white/30">پیامی یافت نشد</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {selected && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6 z-50" onClick={() => setSelected(null)}>
          <div className="glass-strong rounded-2xl p-6 w-full max-w-3xl max-h-[80vh] overflow-y-auto flex flex-col gap-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-white">جزئیات پیام {selected.message_id}</h3>
              <button onClick={() => setSelected(null)} className="glass rounded-full w-8 h-8 flex items-center justify-center">✕</button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="glass rounded-xl p-4">
                <div className="text-xs text-white/40 mb-2">متن اصلی</div>
                <div className="text-sm whitespace-pre-wrap text-white/80 leading-relaxed">{selected.original_text || "(خالی)"}</div>
              </div>
              <div className="glass rounded-xl p-4 border border-violet-500/20">
                <div className="text-xs text-violet-300 mb-2">متن خوشگل‌شده</div>
                <div className="text-sm whitespace-pre-wrap text-white leading-relaxed">{selected.formatted_text || "(بدون تغییر)"}</div>
              </div>
            </div>
            {selected.error && <div className="bg-red-500/10 rounded-xl p-3 text-xs text-red-300">خطا: {selected.error}</div>}
            <div className="text-xs text-white/40">قوانین اعمال‌شده: {selected.applied_rules || "-"} • زمان: {selected.processing_time_ms}ms</div>
          </div>
        </div>
      )}
    </div>
  );
}
