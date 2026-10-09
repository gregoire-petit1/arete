/** Keep one mark per metric: long conversations must not grow the performance buffer. */
export function markWorkout(name: string): void {
  performance.clearMarks(name);
  performance.mark(name);
}
export function measureWorkout(name: string, start: string, end: string): void {
  if (!performance.getEntriesByName(start, 'mark').length || !performance.getEntriesByName(end, 'mark').length) return;
  performance.clearMeasures(name);
  performance.measure(name, start, end);
}
