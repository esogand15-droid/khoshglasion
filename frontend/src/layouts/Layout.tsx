import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  CalendarClock,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Megaphone,
  Menu,
  MessagesSquare,
  ScrollText,
  Settings,
  Smile,
  SwatchBook,
} from "lucide-react";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { Sidebar, SidebarGroup, SidebarItem } from "@/components/ui/sidebar";


const NAV = [
  { to: "/", label: "خانه", icon: LayoutDashboard, end: true },
  { to: "/channels", label: "کانال‌ها", icon: Megaphone },
  { to: "/automation", label: "پست خودکار", icon: CalendarClock },
  { to: "/messages", label: "پیام‌ها", icon: MessagesSquare },
  { to: "/styles", label: "استایل‌ها", icon: SwatchBook },
  { to: "/emojis", label: "ایموجی", icon: Smile },
  { to: "/preview", label: "آزمایش", icon: FlaskConical },
  { to: "/health", label: "سلامت", icon: Activity },
  { to: "/audit", label: "ردپا", icon: ScrollText },
  { to: "/settings", label: "تنظیمات", icon: Settings },
];

function NavItems({ onPick }: { onPick?: () => void }) {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <SidebarItem
        icon={NAV[0].icon}
        label={NAV[0].label}
        href="/"
        active={location.pathname === "/"}
        onClick={(event) => {
          event.preventDefault();
          navigate("/");
          onPick?.();
        }}
      />
      <SidebarGroup title="کار روزانه">
        {NAV.slice(1, 7).map((item) => (
          <SidebarItem
            key={item.to}
            icon={item.icon}
            label={item.label}
            href={item.to}
            active={location.pathname.startsWith(item.to)}
            onClick={(event) => {
              event.preventDefault();
              navigate(item.to);
              onPick?.();
            }}
          />
        ))}
      </SidebarGroup>
      <SidebarGroup title="عملیات">
        {NAV.slice(7).map((item) => (
          <SidebarItem
            key={item.to}
            icon={item.icon}
            label={item.label}
            href={item.to}
            active={location.pathname.startsWith(item.to)}
            onClick={(event) => {
              event.preventDefault();
              navigate(item.to);
              onPick?.();
            }}
          />
        ))}
      </SidebarGroup>
    </>
  );
}

export default function Layout() {
  const location = useLocation();
  const username = useAuth((s) => s.username);
  const role = useAuth((s) => s.role);
  const logout = useAuth((s) => s.logout);
  const navigate = useNavigate();
  const [status, setStatus] = useState<any>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.get("/api/system/health").then((r) => setStatus(r.data)).catch(() => {});
  }, []);

  return (
    <div className="flex min-h-dvh bg-background text-foreground">
      <div className="hidden lg:block">
      <Sidebar
        className="h-dvh rounded-none border-0 border-e"
        header={<span className="text-sm font-bold">خوشگلاسیون</span>}
        footer={
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{username || "ادمین"}</p>
              <p className="text-[11px] text-muted-foreground">{role || "ADMIN"}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              aria-label="خروج"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              <LogOut />
            </Button>
          </div>
        }
      >
        <NavItems />
      </Sidebar>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-border px-4 sm:px-6">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="lg:hidden" aria-label="منو" onClick={() => setOpen(true)}>
              <Menu />
            </Button>
            <span className="text-sm font-bold lg:hidden">خوشگلاسیون</span>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-1.5">
            <Badge variant={status?.bot === "connected" ? "success" : "destructive"}>{status?.bot === "connected" ? "بات زنده" : "بات قطع"}</Badge>
            <Badge variant={status?.database === "connected" ? "success" : "destructive"}>{status?.external_database ? "Postgres" : "دیتابیس"}</Badge>
            {status && status.premium_mode !== "off" && status.premium_mode !== "bot" && (
              <Badge variant={status.user_session_configured ? "success" : "warning"}>{status.user_session_configured ? "نشست وصل" : "نشست قطع"}</Badge>
            )}
            {status?.dry_run && <Badge variant="warning">آزمایشی</Badge>}
            {status?.kill_switch && <Badge variant="destructive">توقف</Badge>}
          </div>
        </header>
        <main className="flex-1 p-4 sm:p-6">
          <div key={location.pathname} className="page-enter">
            <Outlet />
          </div>
        </main>
      </div>

      <Sheet open={open} onOpenChange={setOpen} title="خوشگلاسیون" side="start">
        <nav>
          <NavItems onPick={() => setOpen(false)} />
        </nav>
      </Sheet>
    </div>
  );
}
