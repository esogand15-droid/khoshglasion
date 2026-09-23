import { formatJalali } from "@/lib/jalali";
import { fa } from "@/lib/utils";

export function when(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${formatJalali(date)}، ${date.toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit" })}`;
}

export function count(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return fa(value);
}
