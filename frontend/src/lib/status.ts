export const STATUS: Record<string, string> = {
  edited: "ادیت شد",
  failed: "ناموفق",
  skipped: "رد شد",
  dry_run: "آزمایشی",
  pending_edit: "در صف",
  received: "رسید",
};

export function statusVariant(status: string): "success" | "destructive" | "warning" | "secondary" | "brand" {
  if (status === "edited") return "success";
  if (status === "failed") return "destructive";
  if (status === "dry_run" || status === "pending_edit") return "warning";
  if (status === "skipped") return "secondary";
  return "brand";
}
