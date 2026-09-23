import { useEffect, useState } from "react";
import api from "../services/api";
import { Page } from "../components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
import { SearchInput } from "@/components/ui/search-input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { when } from "@/lib/format";
import { DiffList, TelegramPreview } from "@/lib/telegram";
import { STATUS, statusVariant } from "@/lib/status";
import { fa } from "@/lib/utils";

const LIMIT = 20;

export default function Messages() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<any>(null);

  async function load(nextPage = page, nextStatus = status, nextQ = q) {
    const { data } = await api.get("/api/messages", {
      params: { status: nextStatus || undefined, q: nextQ || undefined, limit: LIMIT, offset: (nextPage - 1) * LIMIT },
    });
    setItems(data.items || []);
    setTotal(data.total || 0);
  }
  useEffect(() => { load(1, status, q).catch(() => {}); }, [status]);

  const pages = Math.max(1, Math.ceil(total / LIMIT));

  return (
    <Page kicker="بایگانی ادیت" title="پیام‌ها" description={`${fa(total)} رکورد واقعی از پردازش‌ها.`}>
      <div className="grid gap-3 md:grid-cols-[1fr_220px_auto] md:items-end">
        <SearchInput value={q} onChange={setQ} onSearch={(value) => { setPage(1); load(1, status, value); }} placeholder="جست‌وجو در متن یا خطا" />
        <Select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          options={[
            { value: "", label: "همه وضعیت‌ها" },
            { value: "edited", label: "ادیت شده" },
            { value: "failed", label: "ناموفق" },
            { value: "skipped", label: "رد شده" },
            { value: "dry_run", label: "آزمایشی" },
            { value: "pending_edit", label: "در انتظار" },
          ]}
        />
        <Button variant="outline" onClick={() => load()}>جستجو</Button>
      </div>

      {items.length ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>پیام</TableHead>
              <TableHead>نوع</TableHead>
              <TableHead>دسته</TableHead>
              <TableHead>وضعیت</TableHead>
              <TableHead>زمان</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <div dir="ltr">{fa(row.message_id)}</div>
                  <div className="text-xs text-muted-foreground" dir="ltr">{row.chat_id}</div>
                </TableCell>
                <TableCell>{row.message_type || "text"}{row.ai_used ? " · AI" : ""}</TableCell>
                <TableCell>{row.category}</TableCell>
                <TableCell><Badge variant={statusVariant(row.status)}>{STATUS[row.status] || row.status}</Badge></TableCell>
                <TableCell className="text-xs text-muted-foreground">{when(row.created_at)}</TableCell>
                <TableCell><Button size="sm" variant="outline" onClick={async () => setSelected((await api.get(`/api/messages/${row.id}`)).data)}>باز</Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : <EmptyState title="موردی نیست" description="فیلتر را بردار یا منتظر اولین پست کانال بمان." />}

      {pages > 1 && <Pagination page={page} total={pages} onChange={(next) => { setPage(next); load(next); }} />}

      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)} size="lg" title={selected ? `پیام ${fa(selected.message_id)}` : undefined}>
        {selected && (
          <div className="space-y-4">
            {selected.error && <p className="text-sm text-warning">{selected.error}</p>}
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <p className="mb-1 text-xs text-muted-foreground">متن اصلی</p>
                <div className="rounded-xl border border-border bg-background/40 p-3 text-sm whitespace-pre-wrap">{selected.original_text}</div>
              </div>
              <div>
                <p className="mb-1 text-xs text-muted-foreground">متن خوشگل</p>
                <TelegramPreview html={selected.html_text} plain={selected.formatted_text} />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              روش: {selected.edit_method || "—"} · تلاش: {fa(selected.attempt_count || 0)} · تصمیم: {selected.decision?.strategy || "—"} · قالب: {selected.selection?.template_id || "—"}
            </p>
            <p className="text-xs text-muted-foreground">{selected.applied_rules}</p>
            <DiffList rows={selected.diff} />
            <div className="flex flex-wrap gap-2">
              <Button variant="brand" onClick={async () => { const { data } = await api.post(`/api/messages/${selected.id}/retry`); setSelected(data.message); load(); }}>پردازش دوباره</Button>
              <Button variant="outline" onClick={async () => { setSelected((await api.post(`/api/messages/${selected.id}/skip`)).data); load(); }}>رد کن</Button>
              {selected.status !== "edited" && (
                <Button variant="destructive" onClick={async () => {
                  if (!confirm("این رکورد از بایگانی حذف شود؟ ادیت کانال برنمی‌گردد.")) return;
                  await api.delete(`/api/messages/${selected.id}`);
                  setSelected(null);
                  load();
                }}>حذف از بایگانی</Button>
              )}
            </div>
          </div>
        )}
      </Dialog>
    </Page>
  );
}
