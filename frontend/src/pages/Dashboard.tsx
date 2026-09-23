import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api from "../services/api";
import { Alerts, Badge, Page, Stat, statusTone, STATUS } from "../components";

function token(name: string, fallback: string) {
  if (typeof document === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api.get("/api/dashboard").then((r) => setData(r.data)).catch(() => setError("داشبورد خوانده نشد."));
    api.get("/api/system/overview").then((r) => setAlerts(r.data.alerts || [])).catch(() => {});
  }, []);
  if (!data && !error) return <div className="skeleton" aria-busy="true" aria-label="در حال خواندن داشبورد" />;
  if (!data) return <div className="alert danger" role="alert">{error}</div>;
  const empty = !data.has_data;
  const accent = token("--color-accent", "#16A34A");
  const muted = token("--color-muted-foreground", "#94A3B8");
  const card = token("--color-card", "#0E1223");
  const border = token("--color-border", "#334155");
  const ink = token("--color-foreground", "#F8FAFC");
  return (
    <Page kicker="عملیات" title="داشبورد" actions={!empty ? <span className="pill">میانگین {data.avg_ms}ms · موفقیت {data.success_rate}%</span> : <span className="pill warn">هنوز پست واقعی نرسیده</span>}>
      <Alerts items={alerts} />
      <div className="grid stats">
        <Stat label="کل پیام‌ها" value={data.total} />
        <Stat label="ادیت شده" value={data.edited} />
        <Stat label="ناموفق" value={data.failed} />
        <Stat label="امروز" value={data.today} />
        <Stat label="با هوش مصنوعی" value={data.ai_used} />
        <Stat label="کانال / ایموجی" value={`${data.channels} / ${data.emojis}`} />
      </div>
      {empty && <div className="card empty-state"><b>داده‌ای برای نمایش نیست</b><span className="tiny">وقتی ربات اولین پست کانال را پردازش کند، همین‌جا عدد واقعی می‌آید. عدد ساختگی نشان داده نمی‌شود.</span></div>}
      <div className="grid cards-3">
        <div className="card">
          <h3>هفت روز اخیر</h3>
          {empty ? <div className="tiny">نمودار بعد از اولین پست پر می‌شود.</div> : (
          <>
          <div className="legend">
            <span className="row"><i className="swatch solid" aria-hidden="true" />خط ممتد: ادیت شده</span>
            <span className="row"><i className="swatch dashed" aria-hidden="true" />خط‌چین: همه پردازش‌ها</span>
          </div>
          <div className="chart-box" role="img" aria-label="نمودار خطی هفت روز. خط ممتد ادیت شده است و خط‌چین همه پردازش‌هاست.">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.per_day}>
                <XAxis dataKey="date" tick={{ fill: muted, fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: muted, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip contentStyle={{ background: card, border: `1px solid ${border}`, borderRadius: 0, color: ink }} />
                <Legend />
                <Line type="monotone" dataKey="edited" name="ادیت شده" stroke={accent} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="count" name="همه" stroke={muted} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="table-wrap">
            <table>
              <caption>جدول همان هفت روز</caption>
              <thead><tr><th>تاریخ</th><th>ادیت شده</th><th>همه</th></tr></thead>
              <tbody>
                {data.per_day?.map((row: any) => (
                  <tr key={row.date}><td className="mono">{row.date}</td><td className="mono">{row.edited}</td><td className="mono">{row.count}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          </>)}
        </div>
        <div className="card">
          <h3>دسته‌ها</h3>
          {data.categories?.map((item: any) => (
            <div key={item.name} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
              <span>{item.name}</span><b className="num">{item.count}</b>
            </div>
          ))}
          {!data.categories?.length && <div className="tiny">هنوز پستی نرسیده.</div>}
          <h3 style={{ marginTop: 16 }}>قالب‌های واقعی</h3>
          {data.templates?.map((item: any) => (
            <div key={item.name} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
              <span>{item.name}</span><b className="num">{item.count}</b>
            </div>
          ))}
          {!data.templates?.length && <div className="tiny">هنوز قالبی ثبت نشده.</div>}
        </div>
      </div>
      <div className="card">
        <h3>آخرین پردازش‌ها</h3>
        <div className="table-wrap">
          <table>
            <thead><tr><th>پیام</th><th>دسته</th><th>وضعیت</th><th>زمان</th></tr></thead>
            <tbody>
              {data.recent?.map((row: any) => (
                <tr key={row.id}>
                  <td className="mono muted">{row.message_id}</td>
                  <td>{row.category}</td>
                  <td><Badge tone={statusTone(row.status) as any}>{STATUS[row.status] || row.status}</Badge></td>
                  <td className="tiny">{row.created_at ? new Date(row.created_at).toLocaleString("fa-IR") : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {!!data.failures?.length && (
        <div className="card">
          <h3>آخرین خطاهای واقعی</h3>
          {data.failures.map((row: any) => <div key={row.id} className="tiny">{row.message_id}: {row.error}</div>)}
        </div>
      )}
    </Page>
  );
}
