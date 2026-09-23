import { useEffect, useState } from "react";
import api from "../services/api";
import { Badge, DiffList, Modal, Page, STATUS, statusTone, TelegramPreview } from "../components";

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
        <label className="field" style={{ maxWidth: 280 }}>
          <span>جستجو در متن یا خطا</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} />
        </label>
        <label className="field" style={{ maxWidth: 180 }}>
          <span>وضعیت</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">همه</option>
            <option value="edited">ادیت شده</option>
            <option value="failed">ناموفق</option>
            <option value="skipped">رد شده</option>
            <option value="dry_run">آزمایشی</option>
          </select>
        </label>
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
          <DiffList rows={selected.diff} />
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn-gold" onClick={async () => {
              const { data } = await api.post(`/api/messages/${selected.id}/retry`);
              setSelected(data.message);
              load();
            }}>پردازش دوباره</button>
            <button className="btn" onClick={async () => {
              setSelected(await (await api.post(`/api/messages/${selected.id}/skip`)).data);
              load();
            }}>رد کن</button>
            {selected.status !== "edited" && <button className="btn-danger" onClick={async () => {
              if (!confirm("این رکورد از بایگانی حذف شود؟ ادیت کانال برنمی‌گردد.")) return;
              await api.delete(`/api/messages/${selected.id}`);
              setSelected(null);
              load();
            }}>حذف از بایگانی</button>}
          </div>
        </Modal>
      )}
    </Page>
  );
}
