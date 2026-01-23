export function isValidEmail(s) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s)
}

export function isStrongPassword(s) {
  if (!s) return false
  return s.length >= 8 && /[A-Z]/.test(s) && /[0-9]/.test(s)
}
