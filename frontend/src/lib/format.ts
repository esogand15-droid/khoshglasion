import { shamsiLabel } from "@/lib/jalali";
import { fa } from "@/lib/utils";

export function when(value?: string | null) {
  if (!value) return "—";
  const label = shamsiLabel(value);
  return label === "ثبت نشده" ? "—" : label;
}

export function count(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return fa(value);
}
