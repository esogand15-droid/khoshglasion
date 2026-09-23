import { useEffect, useState } from "react";
import api from "../services/api";
import { Badge, Modal, Page, STATUS, statusTone, TelegramPreview } from "../components";

export default function Messages() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<any>(null);

  async function load() {
    const { data } = await api.get("/api/messages", { params: { status: status || undefined, q: q || undefined, limit: 60 } });
    setItems(data.items || []);
    setTotal(data.total || 0);
  }
  useEffect(() => { load().catch(() => {}); }, [status]);

  return (
    <Page kicker="بایگانی ادیت" title="پیام‌ها" actions={<span className="pill">{total} رکورد</span>}>
      <div className="row">
        <input style={{ maxWidth: 280 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجو در متن یا خطا" onKeyDown={(e) => e.key === "Enter" && load()} />
        <select style={{ maxWidth: 180 }} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">همه</option>
          <option value="edited">ادیت شده</option>
          <option value="failed">ناموفق</option>
          <option value="skipped">رد شده</option>
          <option value="dry_run">آزمایشی</option>
        </select>
        <button className="btn" onClick={load}>جستجو</button>
      </div>
      <div className="card" style={{ padding: 0 }}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>پیام</th><th>نوع</th><th>دسته</th><th>وضعیت</th><th>دلیل</th><th></th></tr></thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td>{row.message_id}<div className="tiny">{row.chat_id}</div></td>
                  <td>{row.message_type || "text"} {row.ai_used ? "· AI" : ""}</td>
                  <td>{row.category}</td>
                  <td><Badge tone={statusTone(row.status) as any}>{STATUS[row.status] || row.status}</Badge></td>
                  <td className="tiny">{row.error || "—"}</td>
                  <td><button className="btn" onClick={async () => setSelected((await api.get(`/api/messages/${row.id}`)).data)}>باز</button></td>
                </tr>
              ))}
              {!items.length && <tr><td colSpan={6} className="tiny">موردی نیست.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {selected && (
        <Modal title={`پیام ${selected.message_id}`} onClose={() => setSelected(null)}>
          {selected.error && <div className="alert warn">{selected.error}</div>}
          <div className="split" style={{ marginTop: 12 }}>
            <div><div className="tiny">متن اصلی</div><div className="preview-paper">{selected.original_text}</div></div>
            <div><div className="tiny">متن خوشگل</div><TelegramPreview html={selected.html_text} plain={selected.formatted_text} /></div>
          </div>
          <div className="tiny">روش: {selected.edit_method || "—"} · تلاش: {selected.attempt_count || 0} · تصمیم: {selected.decision?.strategy || "—"} · قالب: {selected.selection?.template_id || "—"}</div>
          <div className="tiny">{selected.applied_rules}</div>
          {!!selected.diff?.length && <div className="tiny">{selected.diff.slice(0, 8).map((row: any, index: number) => <div key={index}>{row.kind === "add" ? "+ " : "− "}{row.text}</div>)}</div>}
          <button className="btn-gold" style={{ marginTop: 12 }} onClick={async () => {
            const { data } = await api.post(`/api/messages/${selected.id}/retry`);
            setSelected(data.message);
            load();
          }}>پردازش دوباره</button>
        </Modal>
      )}
    </Page>
  );
}
