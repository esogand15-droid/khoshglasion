import { useEffect, useState } from "react";
import api from "../services/api";
import { Page } from "../components";

export default function Audit() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api.get("/api/system/audit").then((r) => setRows(r.data)).catch(() => {}); }, []);
  return (
    <Page kicker="چه کسی چه کرد" title="ردپا">
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>زمان</th><th>ادمین</th><th>کار</th><th>منبع</th><th>جزئیات</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="tiny">{row.created_at ? new Date(row.created_at).toLocaleString("fa-IR") : "-"}</td>
                <td>{row.admin_username || "—"}</td>
                <td>{row.action}</td>
                <td>{row.resource}</td>
                <td className="tiny">{row.new_value || row.ip_address || "—"}</td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={5} className="tiny">هنوز ردپایی نیست.</td></tr>}
          </tbody>
        </table>
      </div>
    </Page>
  );
}
