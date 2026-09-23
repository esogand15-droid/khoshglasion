import { useEffect, useState } from "react";
import api from "../services/api";
import { Page } from "../components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

function readConfig(raw: string | undefined) {
  try { return JSON.parse(raw || "{}"); } catch { return {}; }
}

export default function Styles() {
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ name: "", slug: "", footer: "", divider: "━━━━━━━━━━━━" });
  const [edit, setEdit] = useState<any>(null);
  const [msg, setMsg] = useState("");
  async function load() { setItems((await api.get("/api/styles")).data); }
  useEffect(() => { load().catch(() => {}); }, []);

  return (
    <Page kicker="هویت بصری" title="استایل و فوتر" description="استایل سفارشی را بساز و در تنظیم کانال انتخاب کن.">
      {msg && <p className="text-sm text-muted-foreground" role="status">{msg}</p>}
      <Card>
        <CardHeader><CardTitle>استایل سفارشی</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="نام"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="شناسه لاتین"><Input dir="ltr" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="rotbeland" /></Field>
            <Field label="فوتر"><Textarea value={form.footer} onChange={(e) => setForm({ ...form, footer: e.target.value })} /></Field>
            <Field label="جداکننده"><Input value={form.divider} onChange={(e) => setForm({ ...form, divider: e.target.value })} /></Field>
          </div>
          <Button variant="brand" onClick={async () => {
            try {
              await api.post("/api/styles", { name: form.name, slug: form.slug, config: { footer: form.footer, divider: form.divider, add_footer: true, enabled: true } });
              setMsg("ساخته شد. در تنظیم کانال انتخابش کن.");
              load();
            } catch (error: any) { setMsg(error.response?.data?.detail || "ساخته نشد"); }
          }}>ساخت استایل</Button>
        </CardContent>
      </Card>

      {items.length ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((style) => {
            const config = readConfig(style.config);
            const footer = config.footer || (style.is_builtin ? style.config : "");
            return (
              <Card key={style.id}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle>{style.name}</CardTitle>
                    {style.is_builtin ? <Badge>داخلی</Badge> : <Badge variant={style.enabled === false ? "secondary" : "success"}>{style.enabled === false ? "خاموش" : "فعال"}</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground" dir="ltr">{style.slug}</p>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="rounded-xl border border-border bg-background/40 p-3 text-sm whitespace-pre-wrap">{typeof footer === "string" ? footer || "بدون فوتر" : "بدون فوتر"}</div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={async () => { await api.post(`/api/styles/${style.id}/duplicate`); setMsg("کپی ساخته شد"); load(); }}>کپی</Button>
                    {!style.is_builtin && <Button size="sm" variant="outline" onClick={() => setEdit({ id: style.id, name: style.name, footer: config.footer || "", divider: config.divider || "", enabled: style.enabled !== false, config })}>ویرایش</Button>}
                    {!style.is_builtin && <Button size="sm" variant="outline" onClick={async () => {
                      await api.patch(`/api/styles/${style.id}`, { config: { ...config, enabled: style.enabled === false } });
                      load();
                    }}>{style.enabled === false ? "روشن" : "خاموش"}</Button>}
                    {!style.is_builtin && <Button size="sm" variant="destructive" onClick={async () => { if (!confirm("این استایل حذف شود؟")) return; await api.delete(`/api/styles/${style.id}`); load(); }}>حذف</Button>}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : <EmptyState title="استایلی نیست" />}

      <Dialog open={!!edit} onOpenChange={(open) => !open && setEdit(null)} title={edit ? `ویرایش ${edit.name}` : undefined}>
        {edit && (
          <div className="space-y-3">
            <Field label="نام"><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="فوتر"><Textarea value={edit.footer} onChange={(e) => setEdit({ ...edit, footer: e.target.value })} /></Field>
            <Field label="جداکننده"><Input value={edit.divider} onChange={(e) => setEdit({ ...edit, divider: e.target.value })} /></Field>
            <div className="flex gap-2">
              <Button variant="brand" onClick={async () => {
                await api.patch(`/api/styles/${edit.id}`, { name: edit.name, config: { ...edit.config, footer: edit.footer, divider: edit.divider, enabled: edit.enabled } });
                setMsg("استایل ذخیره شد");
                setEdit(null);
                load();
              }}>ذخیره</Button>
              <Button variant="outline" onClick={() => setEdit(null)}>انصراف</Button>
            </div>
          </div>
        )}
      </Dialog>
    </Page>
  );
}
