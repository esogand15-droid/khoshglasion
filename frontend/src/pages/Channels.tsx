import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Page } from "../components/page";
import { Alert } from "@/components/ui/alert";
import { useConfirm } from "@/components/ui/alert-dialog";
import { AsyncPage, LoadError } from "@/components/ui/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { fa } from "@/lib/utils";

const EMPTY = { chat_id: "", title: "", username: "" };

function Flag({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm">
      <span>{label}</span>
      <Switch checked={checked} disabled={disabled} onCheckedChange={onChange} />
    </label>
  );
}

export default function Channels() {
  const role = useAuth((state) => state.role);
  const canEdit = !role || role !== "VIEWER";
  const [items, setItems] = useState<any[]>([]);
  const [styles, setStyles] = useState<any[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [msg, setMsg] = useState("");
  const [edit, setEdit] = useState<any>(null);
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const { ask, dialog } = useConfirm();

  async function load() {
    if (ready) setRefreshing(true);
    try {
      const [channels, styleRows] = await Promise.all([api.get("/api/channels", { timeout: 12000 }), api.get("/api/styles", { timeout: 12000 })]);
      setItems(channels.data);
      setStyles(styleRows.data);
      setLoadError("");
    } catch (error: any) {
      setLoadError(error.response?.data?.detail || "کانال‌ها خوانده نشد");
    } finally {
      setReady(true);
      setRefreshing(false);
    }
  }
  useEffect(() => { load(); }, []);

  async function add() {
    const chatId = Number(form.chat_id);
    if (!form.chat_id || Number.isNaN(chatId)) { setMsg("Chat ID عددی است، مثل ‎-100…"); return; }
    try {
      await api.post("/api/channels", { chat_id: chatId, title: form.title || undefined, username: form.username || undefined });
      setForm(EMPTY);
      setMsg("کانال ثبت شد. ربات باید ادمین با دسترسی Edit messages باشد.");
      load();
    } catch (error: any) { setMsg(error.response?.data?.detail || "ثبت نشد"); }
  }

  async function save() {
    await api.patch(`/api/channels/${edit.id}`, {
      title: edit.title, username: edit.username, footer_text: edit.footer_text,
      style_id: edit.style_id || null, notes: edit.notes, skip_keywords: edit.skip_keywords,
      signature_text: edit.signature_text, signature_url: edit.signature_url,
      min_chars: Number(edit.min_chars || 1), edit_delay_seconds: edit.edit_delay_seconds === "" ? null : Number(edit.edit_delay_seconds),
      enabled: edit.enabled, auto_beautify: edit.auto_beautify, emoji_replacement: edit.emoji_replacement,
      header_enabled: edit.header_enabled, preserve_buttons: edit.preserve_buttons,
      ai_rewrite: edit.ai_rewrite === "" ? null : edit.ai_rewrite,
    });
    setEdit(null);
    load();
  }

  if (!ready) {
    return (
      <AsyncPage
        kicker="پوشش کانال"
        title="کانال‌ها"
        description="اگر ربات ادمین کانال شود، کانال خودش ثبت می‌شود. Chat ID منفی است و با ‎-100 شروع می‌شود."
        loading
        skeleton="table"
      />
    );
  }

  return (
    <Page
      kicker="پوشش کانال"
      title="کانال‌ها"
      description="اگر ربات ادمین کانال شود، کانال خودش ثبت می‌شود. Chat ID منفی است و با ‎-100 شروع می‌شود."
      actions={<Button variant="outline" loading={refreshing} onClick={() => load()}><RefreshCw /> تازه‌سازی</Button>}
    >
      {dialog}
      {loadError && <LoadError title={loadError} onRetry={load} />}
      <Card className="p-5">
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Chat ID" htmlFor="chat-id"><Input id="chat-id" dir="ltr" value={form.chat_id} onChange={(e) => setForm({ ...form, chat_id: e.target.value })} placeholder="-100…" /></Field>
          <Field label="عنوان" htmlFor="title"><Input id="title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="یوزرنیم" htmlFor="username"><Input id="username" dir="ltr" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></Field>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="brand" disabled={!canEdit} onClick={add}>افزودن</Button>
          <Button variant="outline" disabled={!canEdit} onClick={async () => { if (!form.chat_id) return; await api.post("/api/channels/sync", { chat_id: Number(form.chat_id) }); load(); }}>خواندن از تلگرام</Button>
        </div>
        {msg && <Alert className="mt-3">{msg}</Alert>}
      </Card>

      {items.length ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>کانال</TableHead>
              <TableHead>Chat ID</TableHead>
              <TableHead>ادیت‌ها</TableHead>
              <TableHead>وضعیت</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((channel) => (
              <TableRow key={channel.id}>
                <TableCell>
                  <b>{channel.title || "بدون عنوان"}</b>
                  <div className="text-xs text-muted-foreground">{channel.username || channel.notes || ""}</div>
                </TableCell>
                <TableCell dir="ltr" className="text-muted-foreground">{channel.chat_id}</TableCell>
                <TableCell numeric>{fa(channel.posts_edited || 0)}</TableCell>
                <TableCell>
                  <Badge variant={channel.enabled && channel.can_edit ? "success" : "destructive"}>
                    {channel.can_edit ? (channel.enabled ? "فعال" : "خاموش") : "بدون دسترسی ادیت"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" disabled={!canEdit} onClick={() => setEdit({ ...channel, ai_rewrite: channel.ai_rewrite ?? "" })}>تنظیم</Button>
                    <Button size="sm" variant="destructive" disabled={!canEdit} onClick={() => ask("کانال حذف شود؟", async () => { await api.delete(`/api/channels/${channel.id}`); load(); })}>حذف</Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : loadError ? null : <EmptyState title="هنوز کانالی نیست" description="Chat ID را بالا وارد کن، یا ربات را ادمین کانال کن." />}

      <Dialog open={!!edit} onOpenChange={(open) => !open && setEdit(null)} size="lg" title={edit?.title || "تنظیم کانال"}>
        {edit && (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="عنوان"><Input value={edit.title || ""} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
              <Field label="استایل">
                <Select
                  value={edit.style_id || ""}
                  onChange={(e) => setEdit({ ...edit, style_id: e.target.value })}
                  options={[{ value: "", label: "خودکار بر اساس محتوا" }, ...styles.map((s) => ({ value: s.slug, label: s.name }))]}
                />
              </Field>
              <Field label="فوتر اختصاصی"><Textarea value={edit.footer_text || ""} onChange={(e) => setEdit({ ...edit, footer_text: e.target.value })} /></Field>
              <Field label="کلمات ممنوع، با ویرگول"><Textarea value={edit.skip_keywords || ""} onChange={(e) => setEdit({ ...edit, skip_keywords: e.target.value })} /></Field>
              <Field label="متن دکمه"><Input value={edit.signature_text || ""} onChange={(e) => setEdit({ ...edit, signature_text: e.target.value })} /></Field>
              <Field label="لینک دکمه"><Input dir="ltr" value={edit.signature_url || ""} onChange={(e) => setEdit({ ...edit, signature_url: e.target.value })} /></Field>
              <Field label="حداقل کاراکتر"><Input type="number" value={edit.min_chars || 1} onChange={(e) => setEdit({ ...edit, min_chars: e.target.value })} /></Field>
              <Field label="تأخیر ادیت (ثانیه، خالی = سراسری)"><Input value={edit.edit_delay_seconds ?? ""} onChange={(e) => setEdit({ ...edit, edit_delay_seconds: e.target.value })} /></Field>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <Flag disabled={!canEdit} label="فعال" checked={!!edit.enabled} onChange={(v) => setEdit({ ...edit, enabled: v })} />
              <Flag disabled={!canEdit} label="خوشگل‌سازی پیام خود ادمین" checked={!!edit.auto_beautify} onChange={(v) => setEdit({ ...edit, auto_beautify: v })} />
              <p className="text-xs text-muted-foreground">این گزینه پستی را ادیت می‌کند که خودت در کانال می‌نویسی. پستی که صف خودکار منتشر کرده دوباره ادیت نمی‌شود.</p>
              <Flag disabled={!canEdit} label="ایموجی" checked={!!edit.emoji_replacement} onChange={(v) => setEdit({ ...edit, emoji_replacement: v })} />
              <Flag disabled={!canEdit} label="حفظ دکمه‌ها" checked={!!edit.preserve_buttons} onChange={(v) => setEdit({ ...edit, preserve_buttons: v })} />
            </div>
            <Field label="هوش مصنوعی">
              <Select
                value={edit.ai_rewrite === "" ? "" : String(edit.ai_rewrite)}
                onChange={(e) => setEdit({ ...edit, ai_rewrite: e.target.value === "" ? "" : e.target.value === "true" })}
                options={[
                  { value: "", label: "سراسری" },
                  { value: "true", label: "اجباری" },
                  { value: "false", label: "خاموش" },
                ]}
              />
            </Field>
            <Button variant="brand" disabled={!canEdit} onClick={save}>ذخیره کانال</Button>
          </div>
        )}
      </Dialog>
    </Page>
  );
}
