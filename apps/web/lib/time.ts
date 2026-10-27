const DAY_MS = 24 * 60 * 60 * 1000;

export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

export function formatDateTime(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(new Date(iso));
}

export function formatDate(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone }).format(new Date(iso));
}

export function formatTime(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat(undefined, { timeStyle: "short", timeZone }).format(new Date(iso));
}

export function formatDayHeading(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone,
  }).format(new Date(iso));
}

export function timeZoneLabel(timeZone: string, at = new Date()): string {
  const part = new Intl.DateTimeFormat(undefined, { timeZone, timeZoneName: "short" })
    .formatToParts(at)
    .find((item) => item.type === "timeZoneName");
  return part ? `${timeZone.replaceAll("_", " ")} (${part.value})` : timeZone;
}

/** Calendar day (YYYY-MM-DD) of an instant in a time zone. */
export function dayKey(iso: string | Date, timeZone?: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone,
  }).format(typeof iso === "string" ? new Date(iso) : iso);
}

function zoneOffsetMs(instant: number, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(new Date(instant));
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value);
  const asUtc = Date.UTC(value("year"), value("month") - 1, value("day"), value("hour"), value("minute"), value("second"));
  return asUtc - instant;
}

/** Converts a wall-clock date and time in `timeZone` to a UTC instant. */
export function zonedToUtc(date: string, time: string, timeZone: string): Date {
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const wall = Date.UTC(year, month - 1, day, hour, minute);
  let instant = wall - zoneOffsetMs(wall, timeZone);
  instant = wall - zoneOffsetMs(instant, timeZone);
  return new Date(instant);
}

export function startOfWeek(date: Date): Date {
  const start = new Date(date);
  start.setHours(0, 0, 0, 0);
  const weekday = (start.getDay() + 6) % 7;
  start.setDate(start.getDate() - weekday);
  return start;
}

export function addDays(date: Date, days: number): Date {
  return new Date(date.getTime() + days * DAY_MS);
}

export function isFuture(iso: string): boolean {
  return new Date(iso).getTime() > Date.now();
}

export function groupByDay<T>(items: T[], instant: (item: T) => string, timeZone?: (item: T) => string) {
  const groups = new Map<string, { label: string; items: T[] }>();
  for (const item of items) {
    const zone = timeZone?.(item);
    const key = dayKey(instant(item), zone);
    const group = groups.get(key) ?? { label: formatDayHeading(instant(item), zone), items: [] };
    group.items.push(item);
    groups.set(key, group);
  }
  return [...groups.entries()].map(([key, group]) => ({ key, ...group }));
}

export function shortId(id: string): string {
  return id.replaceAll("-", "").slice(-6).toUpperCase();
}
