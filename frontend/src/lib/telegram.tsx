import { createElement, useEffect, type ReactNode } from "react";
import { EmojiPreview } from "@/components/EmojiPreview";
import { prefetchEmojiMeta } from "@/lib/emojiMedia";

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

function emojiIds(html: string) {
  return [...html.matchAll(/emoji-id="(\d+)"/g)].map((item) => item[1]);
}

function renderNode(node: Node, key: string): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent;
  if (node.nodeType !== Node.ELEMENT_NODE) return null;
  const el = node as HTMLElement;
  const tag = el.tagName.toLowerCase();
  const children = Array.from(el.childNodes).map((child, index) => renderNode(child, `${key}-${index}`));
  if (tag === "tg-emoji") {
    const id = (el.getAttribute("emoji-id") || "").replace(/\D/g, "");
    const fallback = el.textContent || "";
    if (!id) return fallback;
    return <EmojiPreview key={key} id={id} size={26} inline fallback={fallback} />;
  }
  if (!ALLOWED.has(tag)) return children;
  if (tag === "br") return <br key={key} />;
  if (tag === "a") {
    const href = el.getAttribute("href") || "";
    if (!/^https?:\/\//i.test(href) && !href.startsWith("tg://")) return children;
    return <a key={key} href={href} target="_blank" rel="noreferrer">{children}</a>;
  }
  return createElement(tag, { key }, children);
}

export function TelegramPreview({ html, plain }: { html?: string; plain?: string }) {
  const source = html || "";
  useEffect(() => {
    const ids = emojiIds(source);
    if (ids.length) prefetchEmojiMeta(ids).catch(() => undefined);
  }, [source]);
  if (!source.trim()) return <div className="tg-bubble whitespace-pre-wrap">{plain || ""}</div>;
  const doc = new DOMParser().parseFromString(source, "text/html");
  const nodes = Array.from(doc.body.childNodes).map((node, index) => renderNode(node, `n${index}`));
  return <div className="tg-bubble whitespace-pre-wrap">{nodes}</div>;
}
