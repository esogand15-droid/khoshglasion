import { ReactNode } from "react";

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
      <div className="grid" style={{ gap: 16 }}>{children}</div>
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
  return <div className="card stat"><span>{label}</span><b>{value}</b>{hint && <div className="tiny">{hint}</div>}</div>;
}

export function Badge({ tone = "info", children }: { tone?: "ok" | "warn" | "bad" | "info"; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function Toggle({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <div className="toggle">
      <span>{label}</span>
      <button className={`switch ${on ? "on" : ""}`} onClick={onClick} type="button" aria-label={label}><i /></button>
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="card modal" onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3>{title}</h3>
          <button className="btn" onClick={onClose}>بستن</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Alerts({ items }: { items?: { level: string; text: string }[] }) {
  if (!items?.length) return null;
  return <div className="grid">{items.map((item) => <div key={item.text} className={`alert ${item.level}`}>{item.text}</div>)}</div>;
}

export const STATUS: Record<string, string> = {
  edited: "ادیت شده", skipped: "رد شده", failed: "ناموفق", dry_run: "آزمایشی", pending_edit: "در انتظار",
};
export function statusTone(status: string) {
  if (status === "edited") return "ok";
  if (status === "failed") return "bad";
  if (status === "dry_run") return "warn";
  return "info";
}
