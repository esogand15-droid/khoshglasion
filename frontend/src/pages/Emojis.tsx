import { useEffect, useState } from "react";
import api from "../services/api";
import { Page } from "../components/page";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/input";
import { SearchInput } from "@/components/ui/search-input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fa } from "@/lib/utils";

export default function Emojis() {
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "70" });
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState<any>(null);

  async function load() { setItems((await api.get("/api/emojis")).data); }
  useEffect(() => { load().catch(() => {}); }, []);
  const shown = items.filter((item) => !q || `${item.unicode_emoji} ${item.custom_emoji_id} ${item.category || ""}`.includes(q));

  return (
    <Page
      kicker="کتابخانه متحرک"
      title="ایموجی پرمیوم"
      actions={<Button variant="outline" onClick={async () => { const { data } = await api.get("/api/emojis/export"); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "khoshgelasion-emojis.json"; a.click(); }}>خروجی</Button>}
    >
      <Alert title="چطور ID واقعی بگیری؟">
        به ربات در خصوصی یک پیام با ایموجی پرمیوم فوروارد کن. همان لحظه custom_emoji_id وارد کتابخانه می‌شود. صاحب ربات باید تلگرام پرمیوم داشته باشد.
      </Alert>
      <Card>
        <CardHeader><CardTitle>نگاشت تازه</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-4">
            <Field label="ایموجی"><Input value={form.unicode_emoji} onChange={(e) => setForm({ ...form, unicode_emoji: e.target.value })} /></Field>
            <Field label="custom_emoji_id"><Input dir="ltr" value={form.custom_emoji_id} onChange={(e) => setForm({ ...form, custom_emoji_id: e.target.value })} /></Field>
            <Field label="دسته"><Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></Field>
            <Field label="اولویت"><Input value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} /></Field>
          </div>
          <Button variant="brand" onClick={async () => {
            try {
              await api.post("/api/emojis", { ...form, priority: Number(form.priority), category: form.category || undefined });
              setForm({ unicode_emoji: "", custom_emoji_id: "", category: "", priority: "70" });
              setMsg("اضافه شد");
              load();
            } catch (error: any) { setMsg(error.response?.data?.detail || "ثبت نشد"); }
          }}>افزودن</Button>
          {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-full max-w-xs"><SearchInput value={q} onChange={setQ} placeholder="جست‌وجوی ایموجی یا ID" /></div>
        <Button variant="outline" onClick={async () => { const ids = shown.slice(0, 20).map((item) => item.custom_emoji_id); const { data } = await api.post("/api/emojis/validate", { custom_emoji_ids: ids }); setMsg(`معتبر: ${data.valid?.length || 0} / نامعتبر: ${data.invalid?.length || 0}${data.error ? " · " + data.error : ""}`); }}>اعتبارسنجی ۲۰ تای اول</Button>
        <Button variant="outline" onClick={async () => { await api.post("/api/emojis/cleanup-fake"); load(); }}>حذف IDهای فیک</Button>
      </div>

      {shown.length ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead />
              <TableHead>ID</TableHead>
              <TableHead>منبع</TableHead>
              <TableHead>استفاده</TableHead>
              <TableHead>وضعیت</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="text-xl">{item.unicode_emoji}</TableCell>
                <TableCell dir="ltr" className="text-xs">
                  {item.custom_emoji_id}
                  {item.custom_emoji_id?.startsWith("53683241") && <Badge variant="warning">فیک</Badge>}
                </TableCell>
                <TableCell>{item.category || "—"}<div className="text-xs text-muted-foreground">{item.source || ""}</div></TableCell>
                <TableCell numeric>{fa(item.usage_count || 0)}</TableCell>
                <TableCell><Badge variant={item.enabled ? "success" : "secondary"}>{item.enabled ? "فعال" : "خاموش"}</Badge></TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={() => setEdit({ ...item })}>ویرایش</Button>
                    <Button size="sm" variant="outline" onClick={async () => { await api.patch(`/api/emojis/${item.id}`, { enabled: !item.enabled }); load(); }}>{item.enabled ? "خاموش" : "روشن"}</Button>
                    <Button size="sm" variant="destructive" onClick={async () => { if (!confirm("این نگاشت حذف شود؟")) return; await api.delete(`/api/emojis/${item.id}`); load(); }}>حذف</Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : <EmptyState title="نگاشتی نیست" description="یک ایموجی پرمیوم را به ربات فوروارد کن." />}

      <Dialog open={!!edit} onOpenChange={(open) => !open && setEdit(null)} title="ویرایش نگاشت">
        {edit && (
          <div className="space-y-3">
            <Field label="ایموجی"><Input value={edit.unicode_emoji} onChange={(e) => setEdit({ ...edit, unicode_emoji: e.target.value })} /></Field>
            <Field label="custom_emoji_id"><Input dir="ltr" value={edit.custom_emoji_id} onChange={(e) => setEdit({ ...edit, custom_emoji_id: e.target.value })} /></Field>
            <Field label="دسته"><Input value={edit.category || ""} onChange={(e) => setEdit({ ...edit, category: e.target.value })} /></Field>
            <Field label="اولویت"><Input value={edit.priority} onChange={(e) => setEdit({ ...edit, priority: e.target.value })} /></Field>
            <Button variant="brand" onClick={async () => {
              try {
                await api.patch(`/api/emojis/${edit.id}`, { unicode_emoji: edit.unicode_emoji, custom_emoji_id: edit.custom_emoji_id, category: edit.category || null, priority: Number(edit.priority) });
                setEdit(null);
                setMsg("نگاشت ذخیره شد");
                load();
              } catch (error: any) { setMsg(error.response?.data?.detail || "ذخیره نشد"); }
            }}>ذخیره</Button>
          </div>
        )}
      </Dialog>
    </Page>
  );
}
