export function formatTimestampSeconds(timestamp?: number, locale?: string) {
  if (!timestamp) return '';
  try {
    const date = new Date(timestamp * 1000);
    const options: Intl.DateTimeFormatOptions = {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    };
    return new Intl.DateTimeFormat(locale || undefined, options)
      .format(date)
      .replace(/\//g, '-')
      .replace(/, /g, ' ');
  } catch {
    return '';
  }
}
