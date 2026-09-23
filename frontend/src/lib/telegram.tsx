const ALLOWED = new Set(["b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "blockquote", "tg-spoiler", "tg-emoji", "br"]);

export function sanitizeTelegramHtml(input: string) {
  const doc = new DOMParser().parseFromString(input || "", "text/html");
  const walk = (node: Node): string => {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || "";
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const el = node as HTMLElement;
    const tag = el.tagName.toLowerCase();
    const inner = Array.from(el.childNodes).map(walk).join("");
    if (!ALLOWED.has(tag)) return inner;
    if (tag === "br") return "<br>";
    if (tag === "a") {
      const href = el.getAttribute("href") || "";
      if (!/^https?:\/\//i.test(href) && !href.startsWith("tg://")) return inner;
      return `<a href="${href.replace(/"/g, "")}" target="_blank" rel="noreferrer">${inner}</a>`;
    }
    if (tag === "tg-emoji") {
      const emojiId = (el.getAttribute("emoji-id") || "").replace(/[^\d]/g, "");
      return `<tg-emoji emoji-id="${emojiId}">${inner}</tg-emoji>`;
    }
    return `<${tag}>${inner}</${tag}>`;
  };
  return Array.from(doc.body.childNodes).map(walk).join("");
}

export function DiffList({ rows }: { rows?: { kind: string; text: string }[] }) {
  if (!rows?.length) return null;
  return (
    <ul className="mt-3 space-y-1 text-xs">
      {rows.map((row, index) => (
        <li key={index} className={row.kind === "add" ? "text-success" : "text-destructive"}>
          {row.kind === "add" ? "+ " : "− "}
          {row.text}
        </li>
      ))}
    </ul>
  );
}

export function TelegramPreview({ html, plain }: { html?: string; plain?: string }) {
  const safe = sanitizeTelegramHtml(html || "");
  if (!safe) return <div className="tg-bubble">{plain || ""}</div>;
  return <div className="tg-bubble" dangerouslySetInnerHTML={{ __html: safe }} />;
}
