import { useEffect, useState } from "react";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Page } from "../components/page";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { DiffList, TelegramPreview } from "@/lib/telegram";

const SAMPLE = "هر کتابی که معروفه لزوماً برای تو مناسب نیست.\nیکی از مهم‌ترین تصمیم‌ها توی مسیر کنکور، انتخاب منبعیه که با سطح، هدف و زمان مطالعه‌ات هماهنگ باشه.";

export default function Preview() {
  const role = useAuth((state) => state.role);
  const canEdit = !role || role !== "VIEWER";
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
    <Page
      kicker="قبل از کانال"
      title="میز آزمایش"
      description="خروجی را پیش از انتشار ببین. ایموجی‌های کتابخانه همین‌جا متحرک پخش می‌شوند، نه به‌صورت یونیکد ساده."
      actions={<Button variant="brand" onClick={run} loading={loading}>اجرا</Button>}
    >
      <div className="flex flex-wrap items-center gap-4">
        <div className="w-full max-w-xs">
          <Select
            value={channelId}
            onChange={(e) => setChannelId(e.target.value)}
            options={[{ value: "", label: "استایل خودکار" }, ...channels.map((c) => ({ value: c.id, label: c.title || String(c.chat_id) }))]}
          />
        </div>
        <Checkbox checked={isCaption} onCheckedChange={setIsCaption} label="کپشن" />
        <Checkbox checked={useAi && canEdit} disabled={!canEdit} onCheckedChange={setUseAi} label="بازنویسی هوشمند" />
      </div>
      <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} />
      {result?.error && <Alert variant="destructive">{result.error}</Alert>}
      {result && !result.error && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader><CardTitle>اصل</CardTitle></CardHeader>
            <CardContent><div className="whitespace-pre-wrap text-sm">{result.original}</div></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>خروجی · {result.category}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <TelegramPreview html={result.html_formatted} plain={result.formatted} />
              <p className="text-xs text-muted-foreground">تصمیم: {result.strategy || "—"}{result.ai_used ? " · بازنویسی شد" : " · بدون بازنویسی"}</p>
              <p className="text-xs text-muted-foreground">{result.applied_rules?.join(" · ")}</p>
              {result.warnings?.length > 0 && <Alert variant="warning">{result.warnings.join(" · ")}</Alert>}
              <DiffList rows={result.diff} />
            </CardContent>
          </Card>
        </div>
      )}
    </Page>
  );
}
