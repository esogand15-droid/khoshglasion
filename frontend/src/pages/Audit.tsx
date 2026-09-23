import { useEffect, useState } from "react";
import api from "../services/api";
import { Page } from "../components/page";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { when } from "@/lib/format";

export default function Audit() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api.get("/api/system/audit").then((r) => setRows(r.data)).catch(() => {}); }, []);
  return (
    <Page kicker="چه کسی چه کرد" title="ردپا">
      {rows.length ? (
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
      ) : <EmptyState title="هنوز ردپایی نیست" />}
    </Page>
  );
}
