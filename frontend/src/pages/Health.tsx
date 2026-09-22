import { useEffect, useState } from "react";
import api from "../services/api";

export default function Health() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get("/api/system/health").then((r) => setData(r.data)).catch((e) => setErr(e.response?.data?.detail || "خطا")); }, []);
  if (err) return <div className="text-red-300 text-sm">{err}</div>;
  if (!data) return <div className="text-white/50 text-sm">در حال بررسی...</div>;
  const items = [
    { label: "دیتابیس", value: data.database, ok: data.database === "connected" },
    { label: "بات تلگرام", value: data.bot, ok: data.bot === "connected" },
    { label: "وبهوک", value: data.webhook, ok: !!data.webhook && data.webhook !== "not_set" },
    { label: "Dry Run", value: data.dry_run ? "فعال" : "غیرفعال", ok: !data.dry_run },
    { label: "Safe Mode", value: data.safe_mode ? "فعال" : "غیرفعال", ok: data.safe_mode },
    { label: "Kill Switch", value: data.kill_switch ? "فعال ⛔" : "غیرفعال", ok: !data.kill_switch },
    { label: "محیط", value: data.env, ok: true },
  ];
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-bold text-white">سلامت سیستم</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map((it) => (
          <div key={it.label} className="glass rounded-2xl p-5 flex items-center justify-between">
            <div>
              <div className="text-xs text-white/40">{it.label}</div>
              <div className="text-sm font-medium text-white mt-1 font-mono text-[13px] break-all">{it.value}</div>
            </div>
            <div className={`w-3 h-3 rounded-full ${it.ok ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" : "bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.6)]"}`} />
          </div>
        ))}
      </div>
      <div className="glass rounded-2xl p-5">
        <div className="text-sm font-medium text-white mb-2">راهنما</div>
        <ul className="text-xs text-white/50 leading-6 list-disc list-inside">
          <li>اگر بات Not Configured است: BOT_TOKEN را در Railway Variables تنظیم کن.</li>
          <li>اگر وبهوک Not Set است: WEBHOOK_URL را تنظیم کن (مثلا https://xxx.railway.app/telegram/webhook).</li>
          <li>Dry Run فعال باشد، هیچ پیامی واقعاً ادیت نمی‌شود — برای تست عالیه.</li>
          <li>Kill Switch فعال باشد، تمام پردازش متوقف می‌شود.</li>
        </ul>
      </div>
    </div>
  );
}
