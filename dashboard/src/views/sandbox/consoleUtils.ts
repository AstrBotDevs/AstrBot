const DANGEROUS_CONSOLE_COMMAND_PATTERNS = [
  /(^|[;&|]\s*)rm\s+(?:-[\w-]*r[\w-]*f[\w-]*|-[\w-]*f[\w-]*r[\w-]*)\s+(?:--\s+)?(?:\/(?:\S*)?|~(?:\S*)?|\$HOME(?:\S*)?)(?:\s|$)/i,
  /(^|[;&|]\s*)mkfs(?:\.[\w-]+)?\s+/,
  /(^|[;&|]\s*)dd\s+[^\n]*(?:of=\/dev\/|of=\/)/,
  /(^|[;&|]\s*):\(\)\s*\{\s*:\|:\s*&\s*\}\s*;/,
]

export function isDangerousConsoleCommand(command: string) {
  const normalized = command.trim()
  return DANGEROUS_CONSOLE_COMMAND_PATTERNS.some((pattern) => pattern.test(normalized))
}
