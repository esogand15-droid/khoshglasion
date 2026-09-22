import { useEffect, useState } from "react";
import api from "../services/api";

export default function Settings() {
  const [data, setData] = useState<any>(null);
  const [aiConfig, setAiConfig] = useState<any>({ enabled: false, base_url: "", model: "", api_key: "", prompt_template: "" });
  const [aiTest, setAiTest] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"system" | "ai">("system");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => { 
    api.get("/api/system/settings").then((r) => setData(r.data)).catch(()=>{}); 
    api.get("/api/system/ai/config").then((r) => setAiConfig(r.data)).catch(()=>{});
  }, []);

  const handleSaveAI = async () => {
    setSaving(true);
    try {
      await api.post("/api/system/ai/config", aiConfig);
      setAiTest("✅ تنظیمات AI ذخیره شد (ممکن است نیاز به Restart باشد)");
    } catch (e: any) {
      setAiTest("❌ " + (e.response?.data?.detail || e.message));
    }
    setSaving(false);
  };

  const handleTestAI = async () => {
    setTesting(true);
    setAiTest("🔄 در حال تست اتصال...");
    try {
      const r = await api.post("/api/system/ai/test");
      if (r.data.ok) setAiTest("✅ اتصال موفق — مدل: " + r.data.model);
      else setAiTest("❌ " + r.data.error);
    } catch (e: any) {
      setAiTest("❌ " + (e.response?.data?.detail || e.message));
    }
    setTesting(false);
  };

  if (!data) return <div className="text-white/50 text-sm">در حال بارگذاری...</div>;
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-bold text-white">تنظیمات</h1>
      
      {/* Tabs */}
      <div className="flex gap-2">
        <button 
          onClick={() => setActiveTab("system")}
          className={`px-4 py-2 rounded-xl text-sm font-medium transition ${activeTab === "system" ? "bg-white/10 text-white" : "bg-white/5 text-white/50 hover:bg-white/10"}`}
        >
          سیستم
        </button>
        <button 
          onClick={() => setActiveTab("ai")}
          className={`px-4 py-2 rounded-xl text-sm font-medium transition ${activeTab === "ai" ? "bg-white/10 text-white" : "bg-white/5 text-white/50 hover:bg-white/10"}`}
        >
          🤖 AI Integration
        </button>
      </div>

      {activeTab === "system" && (
        <div className="flex flex-col gap-6">
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
      )}

      {activeTab === "ai" && (
        <div className="flex flex-col gap-6">
          <div className="glass rounded-2xl p-5 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-white">AI Integration</div>
              <span className={`text-xs px-2 py-1 rounded-full ${aiConfig.enabled ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}>
                {aiConfig.enabled ? "فعال" : "غیرفعال"}
              </span>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-white/50 mb-1">Base URL (OpenAI-compatible)</label>
                <input
                  type="text"
                  value={aiConfig.base_url}
                  onChange={e => setAiConfig({...aiConfig, base_url: e.target.value})}
                  placeholder="https://api.openai.com یا https://your-proxy.com"
                  className="w-full glass rounded-xl px-3 py-2 text-white text-sm placeholder-white/30 outline-none focus:ring-2 focus:ring-cyan-500/50"
                />
                <p className="text-[11px] text-white/30 mt-1">مثال: https://api.openai.com, https://openrouter.ai/api/v1, یا پروکسی شخصی</p>
              </div>
              <div>
                <label className="block text-xs text-white/50 mb-1">Model</label>
                <input
                  type="text"
                  value={aiConfig.model}
                  onChange={e => setAiConfig({...aiConfig, model: e.target.value})}
                  placeholder="gpt-4o-mini, gpt-4o, llama-3.1-70b, etc."
                  className="w-full glass rounded-xl px-3 py-2 text-white text-sm placeholder-white/30 outline-none focus:ring-2 focus:ring-cyan-500/50"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs text-white/50 mb-1">API Key</label>
                <input
                  type="password"
                  value={aiConfig.api_key}
                  onChange={e => setAiConfig({...aiConfig, api_key: e.target.value})}
                  placeholder="sk-... یا کلید API پروکسی"
                  className="w-full glass rounded-xl px-3 py-2 text-white text-sm placeholder-white/30 outline-none focus:ring-2 focus:ring-cyan-500/50"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs text-white/50 mb-1">Prompt Template (متغیر {text} جایگزین می‌شود)</label>
                <textarea
                  value={aiConfig.prompt_template}
                  onChange={e => setAiConfig({...aiConfig, prompt_template: e.target.value})}
                  rows={4}
                  className="w-full glass rounded-xl px-3 py-2 text-white text-sm placeholder-white/30 outline-none focus:ring-2 focus:ring-cyan-500/50 resize-none font-mono text-[12px]"
                />
              </div>
              <div className="md:col-span-2 flex gap-3">
                <button
                  onClick={handleSaveAI}
                  disabled={saving}
                  className="flex-1 px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-400 font-medium hover:bg-cyan-500/30 disabled:opacity-50 transition"
                >
                  {saving ? "⏳ ذخیره..." : "💾 ذخیره تنظیمات AI"}
                </button>
                <button
                  onClick={handleTestAI}
                  disabled={testing}
                  className="px-4 py-2 rounded-xl bg-amber-500/20 text-amber-400 font-medium hover:bg-amber-500/30 disabled:opacity-50 transition"
                >
                  {testing ? "🔄 تست..." : "🧪 تست اتصال"}
                </button>
              </div>
            </div>

            {aiTest && (
              <div className={`text-sm p-3 rounded-xl ${aiTest.startsWith("✅") ? "bg-green-500/10 text-green-400" : aiTest.startsWith("❌") ? "bg-red-500/10 text-red-400" : "bg-amber-500/10 text-amber-400"}`}>
                {aiTest}
              </div>
            )}

            <div className="glass rounded-xl p-3 text-xs text-white/40">
              <strong>نحوه کار:</strong> وقتی فعال باشد، هر پستی که در کانال گذاشته می‌شود ابتدا توسط موتور فرمت‌سازی پردازش می‌شود، سپس متن نهایی به AI ارسال می‌شود تا بازنویسی/بهبودی شود (حفظ معنا، اضافه کردن ایموجی، بهبود لحن)، و نتیجه برای ادیت در تلگرام استفاده می‌شود. از OpenAI-compatible endpoints پشتیبانی می‌شود (OpenAI, OpenRouter, Ollama با proxy, و...).
            </div>
          </div>
        </div>
      )}
    </div>
  );
}