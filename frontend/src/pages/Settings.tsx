import { useEffect, useState } from "react";
import api from "../services/api";

export default function Settings() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api.get("/api/system/settings").then((r) => setData(r.data)).catch(()=>{}); }, []);
  if (!data) return <div className="text-white/50 text-sm">در حال بارگذاری...</div>;
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-bold text-white">تنظیمات</h1>
      <div className="glass rounded-2xl p-5 flex flex-col gap-4">
        <div className="text-sm font-medium text-white">وضعیت فعلی (خواندنی — تغییر via متغیر محیطی)</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <div className="glass rounded-xl p-3 flex justify-between"><span className="text-white/50">DRY_RUN</span><span className="font-mono text-white">{String(data.dry_run)}</span></div>
          <div className="glass rounded-xl p-3 flex justify-between"><span className="text-white/50">SAFE_MODE</span><span className="font-mono text-white">{String(data.safe_mode)}</span></div>
          <div className="glass rounded-xl p-3 flex justify-between"><span className="text-white/50">KILL_SWITCH</span><span className="font-mono text-white">{String(data.kill_switch)}</span></div>
          <div className="glass rounded-xl p-3 flex justify-between"><span className="text-white/50">WEBHOOK_URL</span><span className="font-mono text-white text-xs truncate max-w-[200px]">{data.webhook_url || "-"}</span></div>
        </div>
        <p className="text-xs text-white/30">برای تغییر این موارد، متغیرهای محیطی را در Railway ویرایش کن و سرویس را Redeploy کن.</p>
      </div>
      <div className="glass rounded-2xl p-5">
        <div className="text-sm font-medium text-white mb-3">محدودیت‌های تلگرام</div>
        <ul className="text-xs text-white/50 leading-6 list-disc list-inside">
          <li>متن ساده: حداکثر ۴۰۹۶ کاراکتر — کپشن مدیا: ۱۰۲۴ کاراکتر</li>
          <li>پیام‌های نظرسنجی / استیکر / لوکیشن قابل ادیت نیستند — خودکار Skip می‌شود</li>
          <li>Custom Emoji فقط با <code className="glass px-1 py-0.5 rounded text-[11px]">custom_emoji_id</code> معتبر نمایش داده می‌شود — ID را از پنل ایموجی تنظیم کن</li>
          <li>ربات باید ادمین کانال با دسترسی Edit messages باشد</li>
          <li>Rate limit تلگرام خودکار با backoff مدیریت می‌شود</li>
        </ul>
      </div>
    </div>
  );
}
