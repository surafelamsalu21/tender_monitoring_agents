/** FastAPI / Pydantic validation error item */
type ValidationErrorItem = {
  type?: string;
  loc?: (string | number)[];
  msg?: string;
  input?: unknown;
  ctx?: unknown;
};

/**
 * Turn FastAPI `detail` (string, validation array, or object) into display text.
 */
export function formatApiErrorDetail(detail: unknown, fallback = 'Something went wrong.'): string {
  if (detail == null || detail === '') return fallback;
  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => formatValidationItem(item))
      .filter((m): m is string => Boolean(m));
    return messages.length > 0 ? messages.join(' ') : fallback;
  }

  const single = formatValidationItem(detail);
  return single || fallback;
}

function formatValidationItem(item: unknown): string | null {
  if (typeof item === 'string') return item;
  if (!item || typeof item !== 'object') return null;

  const err = item as ValidationErrorItem;
  if (typeof err.msg !== 'string') return null;

  const loc = err.loc?.filter((part) => part !== 'body').join('. ');
  return loc ? `${loc}: ${err.msg}` : err.msg;
}

/** Extract a user-facing message from an axios-style API error. */
export function getApiErrorMessage(err: unknown, fallback: string): string {
  const ax = err as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = ax?.response?.data?.detail;
  if (detail != null) return formatApiErrorDetail(detail, fallback);
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}
