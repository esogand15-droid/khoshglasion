import { useEffect, useState } from "react";
import api from "../services/api";

const STATUS_LABEL: Record<string, string> = {
  edited: "ادیت شده", skipped: "رد شده", failed: "ناموفق", dry_run: "Dry Run", pending_edit: "در انتظار",
};

function statusColor(s: string) {
  if (s === "edited") return "bg-emerald-500/20 text-emerald-300";
  if (s === "failed") return "bg-red-500/20 text-red-300";
  if (s === "dry_run") return "bg-amber-500/20 text-amber-300";
  return "bg-white/10 text-white/60";
}

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
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold text-white">پیام‌ها</h1>
        <div className="flex gap-2">
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="glass rounded-xl px-3 py-2 text-sm bg-transparent outline-none">
            <option value="" className="bg-[#0a0e1a]">همه وضعیت‌ها</option>
            <option value="edited" className="bg-[#0a0e1a]">ادیت شده</option>
            <option value="skipped" className="bg-[#0a0e1a]">رد شده</option>
            <option value="failed" className="bg-[#0a0e1a]">ناموفق</option>
            <option value="dry_run" className="bg-[#0a0e1a]">Dry Run</option>
          </select>
          <button onClick={load} className="glass rounded-xl px-3 py-2 text-xs">↻ تازه‌سازی</button>
        </div>
      </div>

      {/* Hint for skipped */}
      {status === "skipped" && items.length > 0 && (
        <div className="glass rounded-xl p-3 text-xs text-amber-200 bg-amber-500/10">
          نکته: اگر همه پیام‌ها <b>رد شده</b> هستند، دلیل را در ستون <b>دلیل</b> ببین — معمولا <code className="glass px-1 py-0.5 rounded">unknown_channel</code> یا <code className="glass px-1 py-0.5 rounded">no_change</code> است. کانال را درست ثبت کن و مطمئن شو ربات ادمین با دسترسی Edit messages است.
        </div>
      )}

      <div className="glass rounded-2xl p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/40 bg-white/[0.02]"><tr><th className="text-right py-3 px-3">Msg ID</th><th className="text-right py-3">نوع</th><th className="text-right py-3">دسته</th><th className="text-right py-3">وضعیت</th><th className="text-right py-3">دلیل / خطا</th><th className="text-right py-3">زمان</th><th className="text-right py-3">جزئیات</th></tr></thead>
            <tbody>
              {items.map((m) => (
                <tr key={m.id} className="border-t border-white/5 hover:bg-white/[0.02]">
                  <td className="py-3 px-3 font-mono text-white/70">{m.message_id}</td>
                  <td className="py-3 text-white/60">{m.message_type || "-"}</td>
                  <td className="py-3"><span className="glass rounded-full px-2 py-1 text-[11px]">{m.category || "-"}</span></td>
                  <td className="py-3"><span className={`rounded-full px-2 py-1 text-[11px] ${statusColor(m.status)}`}>{STATUS_LABEL[m.status] || m.status}</span></td>
                  <td className="py-3 max-w-[220px] truncate text-white/50 text-[11px]">{m.error ? m.error.slice(0,120) : "-"}</td>
                  <td className="py-3 text-white/40 text-[11px]">{m.created_at ? new Date(m.created_at).toLocaleString("fa-IR") : "-"}</td>
                  <td className="py-3"><button onClick={() => open(m.id)} className="text-violet-400 hover:text-violet-300">نمایش</button></td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={7} className="py-10 text-center text-white/30">پیامی یافت نشد</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {selected && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6 z-50" onClick={() => setSelected(null)}>
          <div className="glass-strong rounded-2xl p-6 w-full max-w-3xl max-h-[80vh] overflow-y-auto flex flex-col gap-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-white">پیام {selected.message_id} — {STATUS_LABEL[selected.status] || selected.status}</h3>
              <button onClick={() => setSelected(null)} className="glass rounded-full w-8 h-8 flex items-center justify-center">✕</button>
            </div>
            {selected.error && <div className={`${selected.status==="failed" ? "bg-red-500/10 text-red-300" : "bg-amber-500/10 text-amber-300"} rounded-xl p-3 text-xs leading-5`}>دلیل: {selected.error}</div>}
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
            <div className="text-xs text-white/40">دسته: {selected.category || "-"} • قوانین: {selected.applied_rules || "-"} • زمان: {selected.processing_time_ms ?? "-"}ms</div>
          </div>
        </div>
      )}
    </div>
  );
}
