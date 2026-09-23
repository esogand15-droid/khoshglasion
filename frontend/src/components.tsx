import { ReactNode, useEffect, useRef } from "react";
import { Icon, IconName } from "./icons";

export function Page({ kicker, title, actions, children }: { kicker?: string; title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <div className="topbar">
        <div>
          {kicker && <div className="kicker">{kicker}</div>}
          <h1>{title}</h1>
        </div>
        <div className="row">{actions}</div>
      </div>
      <div className="grid">{children}</div>
    </section>
  );
}

export function Card({ title, extra, children, className = "" }: { title?: string; extra?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`card ${className}`}>
      {(title || extra) && <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}><h3>{title}</h3>{extra}</div>}
      {children}
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return <div className="card stat"><span>{label}</span><b className="num">{value}</b>{hint && <div className="tiny">{hint}</div>}</div>;
}

const BADGE_ICON: Record<string, IconName> = { ok: "check", bad: "x", warn: "warn", info: "pause" };

export function Badge({ tone = "info", children }: { tone?: "ok" | "warn" | "bad" | "info"; children: ReactNode }) {
  return <span className={`badge ${tone}`}><Icon name={BADGE_ICON[tone]} />{children}</span>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function Toggle({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <div className="toggle">
      <span>{label}</span>
      <button className={`switch ${on ? "on" : ""}`} onClick={onClick} type="button" aria-pressed={on} aria-label={label}><i /></button>
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const node = ref.current;
    const previously = document.activeElement as HTMLElement | null;
    const focusables = () => [...(node?.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])") || [])].filter((el) => !el.hasAttribute("disabled"));
    focusables()[0]?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") { closeRef.current(); return; }
      if (event.key !== "Tab" || !node) return;
      const items = focusables();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previously?.focus();
    };
  }, []);
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="card modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" ref={ref} onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3 id="modal-title">{title}</h3>
          <button className="btn" onClick={onClose}>بستن</button>
        </div>
        {children}
      </div>
    </div>
  );
}

const ALLOWED_TAGS = new Set(["b", "strong", "i", "em", "u", "s", "code", "pre", "blockquote", "a", "tg-emoji", "tg-spoiler", "br"]);

export function sanitizeTelegramHtml(input: string): string {
  if (typeof DOMParser === "undefined") {
    return (input || "").replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch] || ch));
  }
  const doc = new DOMParser().parseFromString(`<div>${input || ""}</div>`, "text/html");
  const root = doc.body.firstElementChild;
  if (!root) return "";
  const walk = (node: Element) => {
    [...node.children].forEach((child) => {
      const tag = child.tagName.toLowerCase();
      if (!ALLOWED_TAGS.has(tag)) {
        child.replaceWith(doc.createTextNode(child.textContent || ""));
        return;
      }
      [...child.attributes].forEach((attr) => {
        const name = attr.name.toLowerCase();
        const value = attr.value || "";
        const keepLink = tag === "a" && name === "href" && /^(https?:|tg:)/i.test(value);
        const keepEmoji = tag === "tg-emoji" && name === "emoji-id" && /^\d+$/.test(value);
        const keepQuote = tag === "blockquote" && name === "expandable";
        const keepLang = tag === "code" && name === "class" && /^language-[A-Za-z0-9_+-]{1,32}$/.test(value);
        if (!keepLink && !keepEmoji && !keepQuote && !keepLang) child.removeAttribute(attr.name);
      });
      walk(child);
    });
  };
  walk(root);
  return root.innerHTML;
}

export function TelegramPreview({ html, plain }: { html?: string | null; plain?: string }) {
  const source = html || (plain || "").replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch] || ch));
  return <div className="tg-bubble" dangerouslySetInnerHTML={{ __html: sanitizeTelegramHtml(source) }} />;
}

export function Alerts({ items }: { items?: { level: string; text: string }[] }) {
  if (!items?.length) return null;
  return <div className="grid">{items.map((item) => <div key={item.text} className={`alert ${item.level}`} role={item.level === "danger" ? "alert" : "status"}>{item.text}</div>)}</div>;
}

export function DiffList({ rows }: { rows?: { kind: string; text: string }[] }) {
  if (!rows?.length) return null;
  return <div className="tiny">{rows.slice(0, 8).map((row, index) => <div key={index} className={row.kind === "add" ? "diff-add" : "diff-del"}>{row.kind === "add" ? "+ " : "− "}{row.text}</div>)}</div>;
}

export const STATUS: Record<string, string> = {
  edited: "ادیت شده", skipped: "رد شده", failed: "ناموفق", dry_run: "آزمایشی", pending_edit: "در انتظار",
};
export function statusTone(status: string) {
  if (status === "edited") return "ok";
  if (status === "failed") return "bad";
  if (status === "dry_run" || status === "pending_edit") return "warn";
  return "info";
}
