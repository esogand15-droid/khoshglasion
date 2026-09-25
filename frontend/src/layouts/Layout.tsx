import { Component, useEffect, useState, type ReactNode } from "react";
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
import { setPanelLight } from "../lib/pace";
import { fa } from "@/lib/utils";
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

class OutletGuard extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed) {
      return (
        <div className="rounded-xl border border-destructive/40 bg-card p-4 text-sm">
          <p className="font-semibold">این بخش خطا داد و صفحه سیاه نماند.</p>
          <button type="button" className="mt-3 cursor-pointer underline" onClick={() => this.setState({ failed: false })}>دوباره نشان بده</button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function Layout() {
  const location = useLocation();
  const username = useAuth((s) => s.username);
  const role = useAuth((s) => s.role);
  const logout = useAuth((s) => s.logout);
  const navigate = useNavigate();
  const [status, setStatus] = useState<any>(null);
  const [open, setOpen] = useState(false);
  const [lightBusy, setLightBusy] = useState(false);
  const canToggle = role !== "VIEWER";

  useEffect(() => {
    api.get("/api/system/pulse", { timeout: 8000 }).then((r) => {
      setStatus(r.data);
      setPanelLight(!!r.data.panel_light);
    }).catch(() => {});
  }, []);

  async function toggleLight() {
    if (!canToggle || lightBusy) return;
    const next = !status?.panel_light;
    setStatus((current: any) => ({ ...(current || {}), panel_light: next }));
    setPanelLight(next);
    setLightBusy(true);
    try {
      const { data } = await api.post("/api/system/pace", { panel_light: next }, { timeout: 8000 });
      setStatus((current: any) => ({ ...(current || {}), panel_light: !!data.panel_light }));
      setPanelLight(!!data.panel_light);
    } catch {
      setStatus((current: any) => ({ ...(current || {}), panel_light: !next }));
      setPanelLight(!next);
    } finally {
      setLightBusy(false);
    }
  }

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
            <Badge variant={status?.bot_configured ? "success" : "destructive"}>{status?.bot_configured ? "بات وصل" : "بات قطع"}</Badge>
            <Badge variant={status?.database === "connected" ? "success" : "destructive"}>{status?.database === "connected" ? "دیتابیس" : "دیتابیس قطع"}</Badge>
            <Badge variant={status?.user_session_configured ? "success" : "warning"}>
              {status?.user_session_configured ? `${fa((status.accounts || []).filter((item: any) => item.enabled).length)} نشست فعال` : "نشست قطع"}
            </Badge>
            {status?.dry_run && <Badge variant="warning">آزمایشی</Badge>}
            {status?.kill_switch && <Badge variant="destructive">توقف</Badge>}
            <Button size="sm" variant={status?.panel_light ? "brand" : "outline"} disabled={!canToggle || lightBusy} onClick={toggleLight}>
              {status?.panel_light ? "حالت سبک روشن" : "حالت سبک"}
            </Button>
          </div>
        </header>
        <main className="flex-1 p-4 sm:p-6">
          <div key={location.pathname} className="page-enter">
            <OutletGuard>
              <Outlet />
            </OutletGuard>
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
