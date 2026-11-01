export function normalizeGroupName(value: unknown): string {
  return String(value || '').toUpperCase().trim()
}

export function groupEquals(a: unknown, b: unknown): boolean {
  return normalizeGroupName(a) === normalizeGroupName(b)
}
