import { useEffect, useState } from "react";
import api from "../services/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api.get("/api/dashboard").then((r) => setData(r.data)).catch(()=>{}); }, []);
  if (!data) return <div className="text-white/50 text-sm">در حال بارگذاری...</div>;
  const cards = [
    { label: "کل پیام‌ها", value: data.total, color: "from-blue-600 to-cyan-500" },
    { label: "ادیت شده", value: data.edited, color: "from-emerald-600 to-teal-500" },
    { label: "رد شده", value: data.skipped, color: "from-zinc-600 to-zinc-500" },
    { label: "ناموفق", value: data.failed, color: "from-red-600 to-orange-500" },
    { label: "امروز", value: data.today, color: "from-violet-600 to-purple-500" },
    { label: "این هفته", value: data.week, color: "from-indigo-600 to-blue-500" },
  ];
  const pie = [
    { name: "ادیت", value: data.edited },
    { name: "رد", value: data.skipped },
    { name: "خطا", value: data.failed },
  ];
  const COLORS = ["#10b981","#71717a","#ef4444"];
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">داشبورد</h1>
        <div className="glass rounded-full px-3 py-1.5 text-xs text-white/60">میانگین پردازش: {data.avg_ms}ms</div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {cards.map((c) => (
          <div key={c.label} className="glass rounded-2xl p-4">
            <div className={`w-8 h-8 rounded-xl bg-gradient-to-br ${c.color} flex items-center justify-center text-white text-sm font-bold`}>{c.value}</div>
            <div className="text-xs text-white/50 mt-3">{c.label}</div>
            <div className="text-lg font-bold text-white">{c.value}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass rounded-2xl p-5 lg:col-span-2">
          <div className="text-sm font-medium text-white mb-4">پیام‌ها در ۷ روز گذشته</div>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.per_day}>
                <XAxis dataKey="date" tick={{ fill: "#ffffff66", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#ffffff66", fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "#1a1f2e", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#fff" }} />
                <Bar dataKey="count" fill="#6366f1" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="glass rounded-2xl p-5">
          <div className="text-sm font-medium text-white mb-4">وضعیت پردازش</div>
          <div className="h-[200px] flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pie} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={4}>
                  {pie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "#1a1f2e", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-3 justify-center text-xs">
            {pie.map((p,i)=><span key={p.name} className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{background:COLORS[i]}} />{p.name}: {p.value}</span>)}
          </div>
        </div>
      </div>
      <div className="glass rounded-2xl p-5">
        <div className="text-sm font-medium text-white mb-3">پیام‌های اخیر</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/40"><tr><th className="text-right py-2 px-2">شناسه</th><th className="text-right py-2">دسته</th><th className="text-right py-2">وضعیت</th><th className="text-right py-2">زمان</th></tr></thead>
            <tbody>
              {data.recent?.map((r:any)=>(
                <tr key={r.id} className="border-t border-white/5">
                  <td className="py-2 px-2 font-mono text-white/70">{r.message_id}</td>
                  <td className="py-2"><span className="glass rounded-full px-2 py-1 text-[11px]">{r.category}</span></td>
                  <td className="py-2"><span className={`rounded-full px-2 py-1 text-[11px] ${r.status==="edited"?"bg-emerald-500/20 text-emerald-300":r.status==="failed"?"bg-red-500/20 text-red-300":"bg-white/10 text-white/60"}`}>{r.status}</span></td>
                  <td className="py-2 text-white/40">{new Date(r.created_at).toLocaleString("fa-IR")}</td>
                </tr>
              ))}
              {(!data.recent || data.recent.length===0) && <tr><td colSpan={4} className="py-6 text-center text-white/30">هنوز پیامی ثبت نشده</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
