/** Format 白饭克数（1 支付宝实付元 = 500g 白饭）。 */
export function formatRiceG(grams: number): string {
  const g = Math.max(0, Math.round(grams));
  return `${g.toLocaleString()}g 白饭`;
}
