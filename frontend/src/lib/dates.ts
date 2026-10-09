/** YYYY-MM-DD in the browser's local time zone (toISOString() would give the UTC day). */
export function toLocalISODate(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Local midnight of a 'YYYY-MM-DD' date; new Date(iso) would read it as UTC midnight,
 *  the previous day west of Greenwich. A trailing time part is ignored. */
export function parseLocalDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d);
}
