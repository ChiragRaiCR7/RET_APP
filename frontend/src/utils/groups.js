export function normalizeGroupName(value) {
  return String(value || '').toUpperCase().trim()
}

export function groupEquals(a, b) {
  return normalizeGroupName(a) === normalizeGroupName(b)
}
