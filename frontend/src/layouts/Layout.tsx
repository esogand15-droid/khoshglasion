import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import api from "../services/api";
import { useAuth } from "../stores/auth";

const NAV = [
  ["/", "داشبورد"],
  ["/channels", "کانال‌ها"],
  ["/messages", "پیام‌ها"],
  ["/emojis", "ایموجی پرمیوم"],
  ["/styles", "استایل و فوتر"],
  ["/preview", "میز آزمایش"],
  ["/health", "سلامت و وبهوک"],
  ["/settings", "اتاق تنظیم"],
  ["/audit", "ردپا"],
];

export default function Layout() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const [overview, setOverview] = useState<any>(null);

  useEffect(() => {
    let stop = false;
    const load = () => api.get("/api/system/overview").then((r) => { if (!stop) setOverview(r.data); }).catch(() => {});
    load();
    const id = setInterval(load, 20000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  const health = overview?.health;
  const runtime = overview?.runtime;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="mark">خ</div>
          <div>
            <b>خوشگلاسیون</b>
            <span>اتاق فرمان رتبه لند</span>
          </div>
        </div>
        <nav className="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => isActive ? "active" : ""}>{label}</NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <div className="tiny">{username} · {health?.bot_info?.username ? `@${health.bot_info.username}` : "ربات وصل نیست"}</div>
          <button className="btn" onClick={() => { logout(); navigate("/login"); }}>خروج</button>
        </div>
      </aside>
      <main className="main">
        <div className="pills" style={{ marginBottom: 18 }}>
          <span className={`pill ${health?.external_database ? "ok" : "bad"}`}>{health?.external_database ? "Postgres پایدار" : "SQLite موقت"}</span>
          <span className={`pill ${health?.bot === "connected" ? "ok" : "bad"}`}>{health?.bot === "connected" ? "بات آنلاین" : "بات قطع"}</span>
          <span className={`pill ${runtime?.ai_ready ? "ok" : "warn"}`}>{runtime?.ai_ready ? "هوش مصنوعی آماده" : "هوش مصنوعی خاموش"}</span>
          <span className={`pill ${runtime?.kill_switch ? "bad" : "ok"}`}>{runtime?.kill_switch ? "توقف اضطراری" : "پردازش روشن"}</span>
          {runtime?.dry_run && <span className="pill warn">حالت آزمایشی</span>}
        </div>
        <Outlet />
      </main>
    </div>
  );
}
