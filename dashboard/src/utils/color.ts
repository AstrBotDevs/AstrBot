/**
 * Color manipulation utilities
 */

export interface RgbColor {
  r: number;
  g: number;
  b: number;
}

export interface HsvColor {
  h: number;
  s: number;
  v: number;
}

export function hexToRgb(hex: string): RgbColor | null {
  if (!hex || typeof hex !== 'string') return null
  hex = hex.replace('#', '')
  if (!/^[0-9A-Fa-f]{3}$|^[0-9A-Fa-f]{6}$/.test(hex)) return null
  if (hex.length === 3) {
    hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2]
  }
  const num = parseInt(hex, 16)
  return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 }
}

export function rgbToHex(r: number, g: number, b: number): string {
  const toHex = (v: number) => Math.max(0, Math.min(255, Math.round(v) || 0))
    .toString(16).padStart(2, '0').toUpperCase()
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}

export function rgbToHsv(r: number, g: number, b: number): HsvColor {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const d = max - min
  let h = 0, s = max === 0 ? 0 : d / max, v = max
  if (max !== min) {
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break
      case g: h = (b - r) / d + 2; break
      case b: h = (r - g) / d + 4; break
    }
    h /= 6
  }
  return {
    h: Math.round(h * 360),
    s: Math.round(s * 100),
    v: Math.round(v * 100)
  }
}

export function hsvToRgb(h: number, s: number, v: number): RgbColor {
  h /= 360; s /= 100; v /= 100
  let r = 0, g = 0, b = 0
  const i = Math.floor(h * 6)
  const f = h * 6 - i
  const p = v * (1 - s)
  const q = v * (1 - f * s)
  const tt = v * (1 - (1 - f) * s)
  switch (i % 6) {
    case 0: r = v; g = tt; b = p; break
    case 1: r = q; g = v; b = p; break
    case 2: r = p; g = v; b = tt; break
    case 3: r = p; g = q; b = v; break
    case 4: r = tt; g = p; b = v; break
    case 5: r = v; g = p; b = q; break
  }
  return {
    r: Math.round(r * 255),
    g: Math.round(g * 255),
    b: Math.round(b * 255)
  }
}

export function parseAnyColor(value: string): RgbColor | null {
  if (!value || typeof value !== 'string') return null
  value = value.trim()

  const hexMatch = value.match(/^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/)
  if (hexMatch) {
    return hexToRgb(hexMatch[0].startsWith('#') ? hexMatch[0] : '#' + hexMatch[0])
  }

  const rgbMatch = value.match(/^rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$/i)
  if (rgbMatch) {
    return {
      r: Math.min(255, parseInt(rgbMatch[1])),
      g: Math.min(255, parseInt(rgbMatch[2])),
      b: Math.min(255, parseInt(rgbMatch[3]))
    }
  }

  const hsvMatch = value.match(/^hsv\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})%?\s*,\s*(\d{1,3})%?\s*\)$/i)
  if (hsvMatch) {
    return hsvToRgb(
      Math.min(360, parseInt(hsvMatch[1])),
      Math.min(100, parseInt(hsvMatch[2])),
      Math.min(100, parseInt(hsvMatch[3]))
    )
  }

  return null
}