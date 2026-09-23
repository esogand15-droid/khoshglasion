import { useEffect, useState } from "react";
import api from "../services/api";
import { DiffList, Page, TelegramPreview } from "../components";

const SAMPLE = "هر کتابی که معروفه لزوماً برای تو مناسب نیست.\nیکی از مهم‌ترین تصمیم‌ها توی مسیر کنکور، انتخاب منبعیه که با سطح، هدف و زمان مطالعه‌ات هماهنگ باشه.";

export default function Preview() {
  const [text, setText] = useState(SAMPLE);
  const [channels, setChannels] = useState<any[]>([]);
  const [channelId, setChannelId] = useState("");
  const [isCaption, setIsCaption] = useState(false);
  const [useAi, setUseAi] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.get("/api/channels").then((r) => setChannels(r.data)).catch(() => {}); }, []);

  async function run() {
    setLoading(true);
    try { setResult((await api.post("/api/preview", { text, is_caption: isCaption, channel_id: channelId || undefined, use_ai: useAi })).data); }
    catch (error: any) { setResult({ error: error.response?.data?.detail || "خطا" }); }
    finally { setLoading(false); }
  }

  return (
    <Page kicker="قبل از کانال" title="میز آزمایش" actions={<button className="btn-gold" onClick={run} disabled={loading}>{loading ? "در حال کار..." : "اجرا"}</button>}>
      <div className="row">
        <select style={{ maxWidth: 260 }} value={channelId} onChange={(e) => setChannelId(e.target.value)}>
          <option value="">استایل خودکار</option>
          {channels.map((c) => <option key={c.id} value={c.id}>{c.title || c.chat_id}</option>)}
        </select>
        <label className="check"><input type="checkbox" checked={isCaption} onChange={(e) => setIsCaption(e.target.checked)} /> کپشن</label>
        <label className="check"><input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} /> بازنویسی هوشمند</label>
      </div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} />
      {result?.error && <div className="alert danger">{result.error}</div>}
      {result && !result.error && (
        <div className="split">
          <div className="card"><h3>اصل</h3><div className="preview-paper">{result.original}</div></div>
          <div className="card"><h3>خروجی · {result.category}</h3><TelegramPreview html={result.html_formatted} plain={result.formatted} /><div className="tiny">تصمیم: {result.strategy || "—"}{result.ai_used ? " · بازنویسی شد" : " · بدون بازنویسی"}</div><div className="tiny">{result.applied_rules?.join(" · ")}</div>{result.warnings?.length > 0 && <div className="alert warn">{result.warnings.join(" · ")}</div>}<div className="tiny">نقل‌قول، لینک عضویت و ایموجی پرمیوم در همین حباب دیده می‌شوند. انیمیشن ایموجی فقط داخل تلگرام پخش می‌شود.</div><DiffList rows={result.diff} /></div>
        </div>
      )}
    </Page>
  );
}
