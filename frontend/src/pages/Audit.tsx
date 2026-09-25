import { useEffect, useState } from "react";
import api from "../services/api";
import { EmptyState } from "@/components/ui/empty-state";
import { AsyncPage } from "@/components/ui/page-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { when } from "@/lib/format";

export default function Audit() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setRows((await api.get("/api/system/audit")).data);
    } catch (e: any) {
      setError(e.response?.data?.detail || "ردپا خوانده نشد");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <AsyncPage
      kicker="چه کسی چه کرد"
      title="ردپا"
      description="هر تغییر مدیریتی با نام ادمین و زمان ثبت می‌شود."
      loading={loading}
      error={error}
      onRetry={load}
      skeleton="table"
    >
      {!error && (rows.length ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>زمان</TableHead>
              <TableHead>ادمین</TableHead>
              <TableHead>کار</TableHead>
              <TableHead>منبع</TableHead>
              <TableHead>جزئیات</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="text-xs text-muted-foreground">{when(row.created_at)}</TableCell>
                <TableCell>{row.admin_username || "—"}</TableCell>
                <TableCell>{row.action}</TableCell>
                <TableCell>{row.resource}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{row.new_value || row.ip_address || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <EmptyState title="هنوز ردپایی نیست" description="بعد از ذخیره، انتشار یا تغییر تنظیم، همین‌جا دیده می‌شود." />
      ))}
    </AsyncPage>
  );
}
