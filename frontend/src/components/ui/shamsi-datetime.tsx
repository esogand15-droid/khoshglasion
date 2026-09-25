import { useState } from "react";
import { jalaliMonthLength, MONTHS, shamsiParts, tehranIso, tehranNowParts } from "@/lib/jalali";
import { fa } from "@/lib/utils";
import { Field } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

/** Date and time picker in the Tehran Jalali calendar. It never opens a Gregorian control. */
export function ShamsiDateTime({
  value,
  disabled,
  onChange,
}: {
  value?: string | null;
  disabled?: boolean;
  onChange: (iso: string) => void;
}) {
  const initial = shamsiParts(value) || tehranNowParts();
  const [parts, setParts] = useState(initial);
  const days = jalaliMonthLength(parts.jy, parts.jm);
  const years = [parts.jy - 1, parts.jy, parts.jy + 1];

  function commit(next: typeof parts) {
    const day = Math.min(next.jd, jalaliMonthLength(next.jy, next.jm));
    const fixed = { ...next, jd: day };
    setParts(fixed);
    onChange(tehranIso(fixed.jy, fixed.jm, fixed.jd, fixed.hour, fixed.minute));
  }

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" dir="rtl">
      <Field label="سال">
        <Select disabled={disabled} value={String(parts.jy)} onChange={(event) => commit({ ...parts, jy: Number(event.target.value) })} options={years.map((year) => ({ value: String(year), label: fa(year) }))} />
      </Field>
      <Field label="ماه">
        <Select disabled={disabled} value={String(parts.jm)} onChange={(event) => commit({ ...parts, jm: Number(event.target.value) })} options={MONTHS.map((label, index) => ({ value: String(index + 1), label }))} />
      </Field>
      <Field label="روز">
        <Select disabled={disabled} value={String(Math.min(parts.jd, days))} onChange={(event) => commit({ ...parts, jd: Number(event.target.value) })} options={Array.from({ length: days }, (_, index) => ({ value: String(index + 1), label: fa(index + 1) }))} />
      </Field>
      <Field label="ساعت تهران">
        <Select
          disabled={disabled}
          value={`${parts.hour}:${parts.minute}`}
          onChange={(event) => {
            const [hour, minute] = event.target.value.split(":").map(Number);
            commit({ ...parts, hour, minute });
          }}
          options={Array.from({ length: 24 * 2 }, (_, index) => {
            const hour = Math.floor(index / 2);
            const minute = index % 2 === 0 ? 0 : 30;
            return { value: `${hour}:${minute}`, label: fa(`${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`) };
          })}
        />
      </Field>
    </div>
  );
}
