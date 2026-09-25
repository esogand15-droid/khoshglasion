/** Tehran clock and Jalali dates. Storage stays UTC; the panel never shows a Gregorian picker. */

const TEHRAN = "Asia/Tehran";
const MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
const FA = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

export function faDigits(value: string | number) {
  return String(value).replace(/\d/g, (digit) => FA[Number(digit)]);
}

function div(value: number, by: number) {
  return Math.trunc(value / by);
}

export function toJalali(gy: number, gm: number, gd: number) {
  const gDay = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  const gy2 = gm > 2 ? gy + 1 : gy;
  let days = 355666 + 365 * gy + div(gy2 + 3, 4) - div(gy2 + 99, 100) + div(gy2 + 399, 400) + gd + gDay[gm - 1];
  let jy = -1595 + 33 * div(days, 12053);
  days %= 12053;
  jy += 4 * div(days, 1461);
  days %= 1461;
  if (days > 365) {
    jy += div(days - 1, 365);
    days = (days - 1) % 365;
  }
  if (days < 186) return { jy, jm: 1 + div(days, 31), jd: 1 + (days % 31) };
  return { jy, jm: 7 + div(days - 186, 30), jd: 1 + ((days - 186) % 30) };
}

export function toGregorian(jy: number, jm: number, jd: number) {
  let year = jy + 1595;
  let days = -355668 + 365 * year + div(year, 33) * 8 + div((year % 33) + 3, 4) + jd + (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
  let gy = 400 * div(days, 146097);
  days %= 146097;
  if (days > 36524) {
    gy += 100 * div(--days, 36524);
    days %= 36524;
    if (days >= 365) days += 1;
  }
  gy += 4 * div(days, 1461);
  days %= 1461;
  if (days > 365) {
    gy += div(days - 1, 365);
    days = (days - 1) % 365;
  }
  let gd = days + 1;
  const leap = gy % 4 === 0 && (gy % 100 !== 0 || gy % 400 === 0);
  const lengths = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let gm = 1;
  while (gm <= 12 && gd > lengths[gm]) {
    gd -= lengths[gm];
    gm += 1;
  }
  return { gy, gm, gd };
}

export function isJalaliLeap(jy: number) {
  return [1, 5, 9, 13, 17, 22, 26, 30].includes(jy % 33);
}

export function jalaliMonthLength(jy: number, jm: number) {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return isJalaliLeap(jy) ? 30 : 29;
}

export function tehranParts(value: Date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TEHRAN,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(value);
  const read = (type: string) => Number(parts.find((part) => part.type === type)?.value || 0);
  return { year: read("year"), month: read("month"), day: read("day"), hour: read("hour"), minute: read("minute") };
}

export function shamsiParts(value: string | Date | null | undefined) {
  const date = value instanceof Date ? value : new Date(value || "");
  if (Number.isNaN(date.getTime())) return null;
  const clock = tehranParts(date);
  const jalali = toJalali(clock.year, clock.month, clock.day);
  return { ...jalali, hour: clock.hour, minute: clock.minute };
}

export function shamsiLabel(value: string | null | undefined) {
  const parts = shamsiParts(value);
  if (!parts) return "ثبت نشده";
  const month = MONTHS[parts.jm - 1] || "";
  return faDigits(`${parts.jd} ${month} ${parts.jy}، ${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`);
}

export function tehranIso(jy: number, jm: number, jd: number, hour: number, minute: number) {
  const day = Math.min(Math.max(1, jd), jalaliMonthLength(jy, jm));
  const gregorian = toGregorian(jy, jm, day);
  const utc = Date.UTC(gregorian.gy, gregorian.gm - 1, gregorian.gd, hour, minute) - 3.5 * 60 * 60 * 1000;
  return new Date(utc).toISOString();
}

export function tehranNowParts() {
  return shamsiParts(new Date()) || { jy: 1405, jm: 7, jd: 1, hour: 9, minute: 0 };
}

export { MONTHS };
