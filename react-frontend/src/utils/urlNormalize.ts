/** Fix common URL artifacts (e.g. spaces before `.pdf`) before API calls. */
export function normalizePageUrl(url: string): string {
  const raw = (url || '').trim();
  if (!raw) return raw;
  try {
    const parsed = new URL(raw);
    parsed.pathname = parsed.pathname
      .replace(/\s+\.([a-z0-9]{1,8})\b/gi, '.$1')
      .split('/')
      .map((seg) => seg.replace(/ /g, '%20'))
      .join('/');
    return parsed.toString();
  } catch {
    return raw.replace(/\s+\.([a-z0-9]{1,8})\b/gi, '.$1');
  }
}
