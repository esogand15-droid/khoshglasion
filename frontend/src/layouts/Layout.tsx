import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../stores/auth";

const nav = [
  { to: "/", label: "داشبورد", icon: "◈" },
  { to: "/channels", label: "کانال‌ها", icon: "📢" },
  { to: "/messages", label: "پیام‌ها", icon: "💬" },
  { to: "/emojis", label: "کتابخانه ایموجی", icon: "😊" },
  { to: "/styles", label: "استایل‌ها", icon: "🎨" },
  { to: "/preview", label: "پیش‌نمایش زنده", icon: "✨" },
  { to: "/health", label: "سلامت سیستم", icon: "🟢" },
  { to: "/settings", label: "تنظیمات", icon: "⚙️" },
];

export default function Layout() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="min-h-screen gradient-bg flex">
      {/* Sidebar */}
      <aside className="w-[260px] shrink-0 glass-strong m-3 rounded-2xl p-4 flex flex-col gap-2 sticky top-3 h-[calc(100vh-24px)] overflow-y-auto scrollbar-thin">
        <div className="flex items-center gap-3 px-2 py-3 mb-2">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center text-lg">👑</div>
          <div>
            <div className="font-bold text-white text-sm">خوشگلاسیون</div>
            <div className="text-[11px] text-white/50">هر پست، یکم خوشگل‌تر ✨</div>
          </div>
        </div>
        <div className="glass rounded-xl px-3 py-2 flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-white/70">بات آنلاین</span>
          <span className="mr-auto text-white/40">{username}</span>
        </div>
        <nav className="flex flex-col gap-1 mt-2">
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition ${isActive ? "bg-white/10 text-white" : "text-white/60 hover:bg-white/5 hover:text-white/90"}`}>
              <span className="text-base">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto pt-4 border-t border-white/5">
          <button onClick={() => { logout(); navigate("/login"); }} className="w-full glass rounded-xl py-2.5 text-sm text-white/60 hover:text-white/90">خروج</button>
        </div>
      </aside>
      {/* Main */}
      <main className="flex-1 p-6 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
