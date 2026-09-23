import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api from "../services/api";
import { Alerts, Badge, Page, Stat, statusTone, STATUS } from "../components";

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  useEffect(() => {
    api.get("/api/dashboard").then((r) => setData(r.data)).catch(() => {});
    api.get("/api/system/overview").then((r) => setAlerts(r.data.alerts || [])).catch(() => {});
  }, []);
  if (!data) return <div className="muted">در حال چیدن اتاق فرمان...</div>;
  return (
    <Page kicker="رتبه لند" title="داشبورد" actions={<span className="pill">میانگین {data.avg_ms}ms · موفقیت {data.success_rate}%</span>}>
      <Alerts items={alerts} />
      <div className="grid stats">
        <Stat label="کل پیام‌ها" value={data.total} />
        <Stat label="ادیت شده" value={data.edited} />
        <Stat label="ناموفق" value={data.failed} />
        <Stat label="امروز" value={data.today} />
        <Stat label="با هوش مصنوعی" value={data.ai_used} />
        <Stat label="کانال / ایموجی" value={`${data.channels} / ${data.emojis}`} />
      </div>
      <div className="grid cards-3">
        <div className="card">
          <h3>هفت روز اخیر</h3>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.per_day}>
                <XAxis dataKey="date" tick={{ fill: "#a79d8e", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#a79d8e", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "#16140f", border: "1px solid rgba(226,196,140,.2)", borderRadius: 12 }} />
                <Bar dataKey="edited" fill="#e2b56a" radius={[7, 7, 0, 0]} />
                <Bar dataKey="count" fill="#3d3830" radius={[7, 7, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3>دسته‌ها</h3>
          {data.categories?.map((item: any) => (
            <div key={item.name} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
              <span>{item.name}</span><b>{item.count}</b>
            </div>
          ))}
          {!data.categories?.length && <div className="tiny">هنوز پستی نرسیده.</div>}
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
                  <td className="muted">{row.message_id}</td>
                  <td>{row.category}</td>
                  <td><Badge tone={statusTone(row.status) as any}>{STATUS[row.status] || row.status}</Badge></td>
                  <td className="tiny">{row.created_at ? new Date(row.created_at).toLocaleString("fa-IR") : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Page>
  );
}
