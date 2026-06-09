export const EMAIL_ALREADY_EXISTS_MESSAGE =
  "This email is already registered. Sign in instead, or use Forgot password if you don't remember your password.";

export function isEmailAlreadyExistsError(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes("already registered") ||
    lower.includes("email already") ||
    lower.includes("email is already")
  );
}

export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}
