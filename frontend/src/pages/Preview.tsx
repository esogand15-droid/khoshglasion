import { useState, useEffect } from "react";
import api from "../services/api";

export default function Preview() {
  const [text, setText] = useState("هر کتابی که معروفه لزوماً برای تو مناسب نیست!\n\nیکی از مهمترین تصمیم‌ها توی مسیر کنکور، انتخاب منبعیه که با سطح، هدف و زمان مطالعه‌ات هماهنگ باشه.\n\nچطور منبع مناسب هر درس رو انتخاب کنیم؟\nآیا واقعاً به چند منبع نیاز داریم؟\nچه زمانی منبع دوم لازمه؟\nو چرا گاهی زیاد بودن منابع، بیشتر از اینکه کمکتون کنه، باعث سردرگمی میشه؟");
  const [isCaption, setIsCaption] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState<any[]>([]);
  const [channelId, setChannelId] = useState("");

  useEffect(() => { api.get("/api/channels").then((r) => setChannels(r.data)).catch(()=>{}); }, []);

  async function run() {
    setLoading(true);
    try {
      const { data } = await api.post("/api/preview", { text, is_caption: isCaption, channel_id: channelId || undefined });
      setResult(data);
    } catch (e: any) { setResult({ error: e.response?.data?.detail || "خطا" }); }
    finally { setLoading(false); }
  }
  useEffect(() => { run(); }, []);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-bold text-white">پیش‌نمایش زنده ✨</h1>
      <p className="text-sm text-white/50">متن را وارد کن تا خروجی خوشگلاسیون را ببینی — بدون اینکه پیامی در تلگرام ادیت شود.</p>

      <div className="flex flex-wrap gap-3 items-center">
        <select value={channelId} onChange={(e) => setChannelId(e.target.value)} className="glass rounded-xl px-3 py-2 text-sm bg-transparent outline-none">
          <option value="" className="bg-[#0a0e1a]">بدون کانال (استایل خودکار)</option>
          {channels.map((c) => <option key={c.id} value={c.id} className="bg-[#0a0e1a]">{c.title || c.chat_id}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm text-white/70">
          <input type="checkbox" checked={isCaption} onChange={(e) => setIsCaption(e.target.checked)} />
          کپشن (محدودیت ۱۰۲۴)
        </label>
        <button onClick={run} disabled={loading} className="bg-gradient-to-r from-violet-600 to-blue-600 rounded-xl px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50">
          {loading ? "در حال پردازش..." : "تست خوشگلاسیون"}
        </button>
      </div>

      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} placeholder="متن کانال را اینجا وارد کن..." className="glass rounded-2xl p-4 text-sm bg-transparent outline-none placeholder:text-white/30 resize-y" />

      {result && !result.error && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Original */}
          <div className="glass rounded-2xl p-0 overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
              <span className="text-sm font-medium text-white/70">پیام اصلی</span>
              <span className="text-[11px] text-white/30">{result.category} • {result.style}</span>
            </div>
            <div className="p-4 flex-1 bg-[#0e1621] m-3 rounded-xl">
              <div className="text-xs text-[#e8a735] mb-2">رتبه لند | مشاوره و آموزش کنکور</div>
              <div className="text-sm whitespace-pre-wrap text-white leading-relaxed">{result.original}</div>
              <div className="mt-4 space-y-1">
                <div className="h-px bg-[#e8a735]/50 w-full" />
                <div className="h-px bg-[#e8a735]/30 w-2/3" />
              </div>
              <div className="mt-3 text-xs text-white/60">📍 عضویت در کانال مشاوره رتبه لند<br />👩‍💻 رزرو مشاوره خصوصی: <span className="text-[#5aa9e6]">@Rotbeland_support</span></div>
            </div>
          </div>
          {/* Formatted */}
          <div className="glass rounded-2xl p-0 overflow-hidden flex flex-col border border-violet-500/20">
            <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between bg-violet-500/5">
              <span className="text-sm font-medium text-violet-300">خروجی خوشگلاسیون ✨</span>
              <span className={`text-[11px] rounded-full px-2 py-0.5 ${result.changed ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-white/40"}`}>{result.changed ? "تغییر کرد" : "بدون تغییر"}</span>
            </div>
            <div className="p-4 flex-1 bg-[#0e1621] m-3 rounded-xl">
              <div className="text-xs text-[#e8a735] mb-2">رتبه لند | مشاوره و آموزش کنکور</div>
              <div className="text-sm whitespace-pre-wrap text-white leading-relaxed">{result.formatted}</div>
              {result.warnings?.length > 0 && <div className="mt-3 text-[11px] text-amber-300">هشدار: {result.warnings.join(", ")}</div>}
              <div className="mt-2 text-[11px] text-white/30">قوانین: {result.applied_rules?.join(", ") || "—"}</div>
            </div>
          </div>
        </div>
      )}
      {result?.error && <div className="bg-red-500/10 rounded-xl p-3 text-sm text-red-300">{result.error}</div>}
    </div>
  );
}
