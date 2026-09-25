import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Inbox } from "lucide-react";
import api from "../services/api";
import { Page } from "../components/page";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { BarChart, LineChart, Sparkline } from "@/components/ui/chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Progress } from "@/components/ui/progress";
import { AsyncPage } from "@/components/ui/page-state";
import { Stat } from "@/components/ui/stat";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Timeline } from "@/components/ui/timeline";
import { formatJalali, shamsiParts } from "@/lib/jalali";
import { when } from "@/lib/format";
import { STATUS, statusVariant } from "@/lib/status";
import { fa, faNumber } from "@/lib/utils";

function alertVariant(level: string): "destructive" | "warning" | "info" {
  if (level === "danger" || level === "error") return "destructive";
  if (level === "warn" || level === "warning") return "warning";
  return "info";
}

function tehranClock(value: string) {
  const parts = shamsiParts(value);
  if (!parts) return "—";
  return fa(`${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`);
}

function tehranDay(value: string) {
  const parts = shamsiParts(value);
  if (!parts) return "—";
  return fa(`${parts.jy}/${String(parts.jm).padStart(2, "0")}/${String(parts.jd).padStart(2, "0")}`);
}

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const dash = await api.get("/api/dashboard");
      setData(dash.data);
      api.get("/api/system/overview").then((r) => setAlerts(r.data.alerts || [])).catch(() => {});
    } catch {
      setError("داشبورد خوانده نشد.");
    }
  }

  useEffect(() => { load(); }, []);

  if (!data) {
    return (
      <AsyncPage
        kicker="عملیات"
        title="داشبورد"
        description={formatJalali(new Date(), { weekday: true })}
        loading={!error}
        error={error}
        onRetry={load}
        skeleton="stats"
      />
    );
  }

  const empty = !data.has_data;
  const days = data.per_day || [];
  const today = days.at(-1);
  const yesterday = days.at(-2);
  const delta = yesterday?.count ? ((today.count - yesterday.count) / yesterday.count) * 100 : undefined;
  const chart = days.map((row: any) => ({ label: tehranDay(row.start || row.date), value: row.edited }));
  const spark = days.map((row: any) => row.edited);

  return (
    <Page
      kicker="عملیات"
      title="داشبورد"
      description={formatJalali(new Date(), { weekday: true })}
      actions={empty ? <Badge variant="warning">هنوز پست واقعی نرسیده</Badge> : <Badge variant="brand">میانگین {fa(data.avg_ms)} میلی‌ثانیه</Badge>}
    >
      {alerts.map((item, index) => (
        <Alert key={item.code || index} variant={alertVariant(item.level)}>
          <span>{item.text}</span>
          {item.fix_path && <Link className="mt-2 block font-medium underline" to={item.fix_path}>{item.fix_label || "رفع در پنل"}</Link>}
        </Alert>
      ))}
      {data.queue?.last_error && (
        <Alert variant="destructive" title={data.queue.last_error}>
          <Link className="font-medium underline" to="/automation">برو به صف و از همان‌جا درستش کن</Link>
        </Alert>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="پیش‌نویس منتظر" value={fa(data.queue?.preview || 0)} />
        <Stat label="زمان‌بندی‌شده" value={fa(data.queue?.scheduled || 0)} />
        <Stat label="شکست امروز" value={fa(data.queue?.failed_today || 0)} />
        <Stat label="ساعت بعدی" value={data.queue?.next_slot ? tehranClock(data.queue.next_slot) : "—"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div
          className="relative overflow-hidden rounded-2xl border border-border bg-card p-6 lg:col-span-2"
          style={{ backgroundImage: "radial-gradient(70% 90% at 100% 0%, oklch(from var(--brand) l c h / 18%), transparent 70%)" }}
        >
          <p className="text-sm text-muted-foreground">پیام‌های پردازش‌شده</p>
          <p className="mt-2 text-3xl font-bold sm:text-4xl">{empty ? "—" : faNumber(data.total)}</p>
          <p className="mt-2 text-sm text-muted-foreground">
            {empty ? "عدد ساختگی نشان داده نمی‌شود. اولین پست کانال که برسد، همین‌جا می‌آید." : `${fa(data.edited)} ادیت شده · ${fa(data.failed)} ناموفق`}
          </p>
          {!empty && spark.some((n: number) => n > 0) && <Sparkline className="mt-5" data={spark} positive={data.failed === 0} />}
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
          <Stat size="sm" label="امروز" value={fa(data.today)} delta={empty ? undefined : delta} deltaLabel="نسبت به دیروز" />
          <Stat size="sm" label="کانال / ایموجی فعال" value={`${fa(data.channels)} / ${fa(data.emojis)}`} />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="ادیت شده" value={fa(data.edited)} />
        <Stat label="ناموفق" value={fa(data.failed)} />
        <Stat label="رد شده" value={fa(data.skipped)} />
        <Stat label="با هوش مصنوعی" value={fa(data.ai_used)} />
      </div>

      {data.success_rate != null && (
        <Card>
          <CardContent className="pt-5">
            <Progress value={data.success_rate} label="نرخ ادیت موفق" showValue />
          </CardContent>
        </Card>
      )}

      {empty ? (
        <EmptyState icon={Inbox} title="داده‌ای برای نمایش نیست" description="وقتی ربات اولین پست کانال را پردازش کند، نمودار و جدول با عدد واقعی پر می‌شوند." />
      ) : (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle>هفت روز اخیر</CardTitle>
              <p className="text-xs text-muted-foreground">خط کهربایی، ادیت‌های موفق است.</p>
            </CardHeader>
            <CardContent>
              <LineChart data={chart} height={220} />
              <Table className="mt-4">
                <TableHeader>
                  <TableRow>
                    <TableHead>تاریخ</TableHead>
                    <TableHead>ادیت شده</TableHead>
                    <TableHead>همه</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {days.map((row: any) => (
                    <TableRow key={row.date}>
                      <TableCell>{tehranDay(row.start || row.date)}</TableCell>
                      <TableCell numeric>{fa(row.edited)}</TableCell>
                      <TableCell numeric>{fa(row.count)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <div className="space-y-4">
            <Card>
              <CardHeader><CardTitle>دسته‌ها</CardTitle></CardHeader>
              <CardContent>
                {data.categories?.length ? (
                  <BarChart data={data.categories.map((item: any) => ({ label: item.name, value: item.count }))} height={160} />
                ) : (
                  <EmptyState title="هنوز دسته‌ای نیست" />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>قالب‌های واقعی</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {data.templates?.length ? data.templates.map((item: any) => (
                  <div key={item.name} className="flex items-center justify-between text-sm">
                    <span>{item.name}</span>
                    <span className="font-semibold tabular-nums">{fa(item.count)}</span>
                  </div>
                )) : <p className="text-xs text-muted-foreground">هنوز قالبی ثبت نشده.</p>}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>آخرین پردازش‌ها</CardTitle></CardHeader>
        <CardContent>
          {data.recent?.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>پیام</TableHead>
                  <TableHead>دسته</TableHead>
                  <TableHead>وضعیت</TableHead>
                  <TableHead>زمان</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.recent.map((row: any) => (
                  <TableRow key={row.id}>
                    <TableCell dir="ltr" className="text-muted-foreground">{fa(row.message_id)}</TableCell>
                    <TableCell>{row.category}</TableCell>
                    <TableCell><Badge variant={statusVariant(row.status)}>{STATUS[row.status] || row.status}</Badge></TableCell>
                    <TableCell className="text-xs text-muted-foreground">{when(row.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : <EmptyState title="هنوز پردازشی نیست" />}
        </CardContent>
      </Card>

      {!!data.failures?.length && (
        <Card>
          <CardHeader><CardTitle>آخرین خطاهای واقعی</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Link className="text-sm font-medium underline" to="/automation">برو به صف و از همان‌جا درستش کن</Link>
            <Timeline
              items={data.failures.map((row: any) => ({
                date: row.created_at ? new Date(row.created_at) : "—",
                title: `پیام ${fa(row.message_id)}`,
                description: row.error || "بدون توضیح",
              }))}
            />
          </CardContent>
        </Card>
      )}
    </Page>
  );
}
