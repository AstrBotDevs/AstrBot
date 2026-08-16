/** Build the header accepted by Dashboard high-risk endpoints. */
export function stepUpHeaders(token: string): Record<string, string> {
  return { 'X-AstrBot-Step-Up': token };
}
