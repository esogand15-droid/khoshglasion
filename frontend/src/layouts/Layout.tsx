import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Icon, IconName } from "../icons";
import api from "../services/api";
import { useAuth } from "../stores/auth";

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: "/", label: "داشبورد", icon: "grid" },
  { to: "/channels", label: "کانال‌ها", icon: "channels" },
  { to: "/messages", label: "پیام‌ها", icon: "messages" },
  { to: "/emojis", label: "ایموجی پرمیوم", icon: "emoji" },
  { to: "/styles", label: "استایل و فوتر", icon: "styles" },
  { to: "/preview", label: "میز آزمایش", icon: "preview" },
  { to: "/health", label: "سلامت و وبهوک", icon: "health" },
  { to: "/settings", label: "اتاق تنظیم", icon: "settings" },
  { to: "/audit", label: "ردپا", icon: "audit" },
];

export default function Layout() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const [overview, setOverview] = useState<any>(null);
  const [paused, setPaused] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    mainRef.current?.focus();
  }, [location.pathname]);

  useEffect(() => {
    let stop = false;
    const load = () => api.get("/api/system/overview").then((r) => {
      if (stop) return;
      setOverview(r.data);
      setUpdatedAt(new Date());
      setStale(false);
    }).catch(() => { if (!stop) setStale(true); });
    load();
    if (paused) return () => { stop = true; };
    const id = setInterval(load, 20000);
    return () => { stop = true; clearInterval(id); };
  }, [paused]);

  useEffect(() => {
    if (!updatedAt || paused) return;
    const id = setTimeout(() => setStale(true), 60000);
    return () => clearTimeout(id);
  }, [updatedAt, paused]);

  const health = overview?.health;
  const runtime = overview?.runtime;
  const flags = overview ? [
    { ok: !!health?.external_database, text: health?.external_database ? "Postgres پایدار" : "SQLite موقت" },
    { ok: health?.bot === "connected", text: health?.bot === "connected" ? "بات آنلاین" : "بات قطع" },
    { ok: !!runtime?.ai_ready, warn: !runtime?.ai_ready, text: runtime?.ai_ready ? "هوش مصنوعی آماده" : "هوش مصنوعی خاموش" },
    { ok: !runtime?.kill_switch, text: runtime?.kill_switch ? "توقف اضطراری" : "پردازش روشن" },
    ...(runtime?.dry_run ? [{ ok: false, warn: true, text: "حالت آزمایشی" }] : []),
  ] : [];
  const live = Boolean(overview && updatedAt && !stale && !paused);
  const clock = updatedAt ? updatedAt.toLocaleTimeString("fa-IR") : "—";
  const liveText = paused
    ? `به‌روزرسانی متوقف است. آخرین داده ${clock}`
    : stale
      ? `وضعیت کهنه است. آخرین داده ${clock}`
      : live
        ? `وضعیت زنده تا ${clock}`
        : "در حال خواندن وضعیت";

  return (
    <div className="app-shell">
      <a className="skip" href="#content">پرش به محتوا</a>
      <aside className="sidebar">
        <div className="brand">
          <div className="mark" aria-hidden="true">خ</div>
          <div>
            <b>خوشگلاسیون</b>
            <span>اتاق فرمان رتبه لند</span>
          </div>
        </div>
        <nav className="nav" aria-label="اصلی">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className={({ isActive }) => isActive ? "active" : ""}>
              <Icon name={item.icon} />{item.label}
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <div className="tiny">{username} · {health?.bot_info?.username ? `@${health.bot_info.username}` : "ربات وصل نیست"}</div>
          <button className="btn-danger" onClick={() => { logout(); navigate("/login"); }}><Icon name="logout" />خروج</button>
        </div>
      </aside>
      <main className="main" id="content" tabIndex={-1} ref={mainRef}>
        <nav className="mobile-nav" aria-label="اصلی">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className={({ isActive }) => isActive ? "active" : ""}>
              <Icon name={item.icon} />{item.label}
            </NavLink>
          ))}
        </nav>
        <section className="status-bar" aria-label="وضعیت عملیات">
          <div className="status-flags">
            {flags.map((flag) => (
              <span key={flag.text} className={`pill ${flag.ok ? "ok" : flag.warn ? "warn" : "bad"}`}>
                <Icon name={flag.ok ? "check" : flag.warn ? "warn" : "x"} />{flag.text}
              </span>
            ))}
            {!overview && <span className="pill warn"><Icon name="warn" />وضعیت هنوز نرسیده</span>}
          </div>
          <div className="status-meta">
            <div className="live-label" role="status"><strong>{live ? "زنده" : paused ? "متوقف" : "کهنه"}</strong> · {liveText}</div>
            <button className="btn" type="button" onClick={() => setPaused((value) => !value)} aria-pressed={paused}>
              <Icon name={paused ? "play" : "pause"} />{paused ? "ادامه به‌روزرسانی" : "توقف به‌روزرسانی"}
            </button>
          </div>
        </section>
        <Outlet />
      </main>
    </div>
  );
}
