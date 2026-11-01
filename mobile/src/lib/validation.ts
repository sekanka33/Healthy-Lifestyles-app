/** Client-side checks mirror the server's rules (the server stays authoritative). */
export function validateEmail(email: string): string | null {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) ? null : 'Enter a valid email address.';
}

export function validatePassword(pw: string): string | null {
  if (pw.length < 10) return 'Use at least 10 characters.';
  if (pw.length > 128) return 'Use at most 128 characters.';
  if (new Set(pw).size < 4) return 'That password is too simple.';
  return null;
}

export function validateCode(code: string): string | null {
  return /^\d{6}$/.test(code) ? null : 'Enter the 6-digit code.';
}
