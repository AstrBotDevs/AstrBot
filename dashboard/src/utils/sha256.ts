/**
 * Lightweight SHA-256 helper utilities for the dashboard frontend.
 *
 * Behavior:
 * - Prefer Web Crypto API (browser / webworker): `crypto.subtle.digest`.
 * - If unavailable and running under Node.js, try to use Node's `crypto` module.
 * - If neither is available, functions throw a clear error (explicit failure is preferred
 *   to returning a silently-wrong value).
 *
 * Exports:
 * - sha256ArrayBuffer(input: string): Promise<ArrayBuffer>
 * - sha256Hex(input: string): Promise<string>
 * - sha256Base64(input: string): Promise<string>
 * - sha256HexSync(input: string): string  // sync helper only available when Node crypto is present; otherwise throws
 *
 * Notes:
 * - All async functions accept a UTF-8 string and return the digest for the UTF-8 bytes of that string.
 * - This file intentionally avoids adding third-party deps and uses standard platform crypto primitives.
 */

type MaybeNodeCrypto = {
  createHash?: (algo: string) => { update: (data: any) => any; digest: (enc?: string) => any };
  webcrypto?: Crypto;
} | null;

/**
 * Compute SHA-256 digest as an ArrayBuffer.
 * Throws a descriptive Error if no suitable crypto provider is found.
 */
export async function sha256ArrayBuffer(input: string): Promise<ArrayBuffer> {
  // Use Web Crypto if available (recommended for browsers)
  const subtle = (globalThis as any)?.crypto?.subtle;
  if (subtle && typeof subtle.digest === "function") {
    const enc = new TextEncoder();
    return await subtle.digest("SHA-256", enc.encode(input));
  }

  // Fallback: attempt to use Node's crypto module dynamically
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires, @typescript-eslint/no-unsafe-assignment
    const nodeCrypto: MaybeNodeCrypto = (typeof require !== "undefined" ? require("crypto") : null);
    if (nodeCrypto) {
      // If Node has a WebCrypto-compatible `webcrypto`
      if ((nodeCrypto as any).webcrypto && typeof (nodeCrypto as any).webcrypto.subtle?.digest === "function") {
        const enc = new TextEncoder();
        return await (nodeCrypto as any).webcrypto.subtle.digest("SHA-256", enc.encode(input));
      }

      // Otherwise use createHash -> Buffer -> ArrayBuffer
      if (typeof (nodeCrypto as any).createHash === "function") {
        const hashBuffer: Buffer = (nodeCrypto as any).createHash("sha256").update(input).digest();
        // Buffer is backed by an ArrayBuffer; ensure we return an ArrayBuffer slice that represents the bytes
        return hashBuffer.buffer.slice(hashBuffer.byteOffset, hashBuffer.byteOffset + hashBuffer.byteLength);
      }
    }
  } catch (e) {
    // fall through to error below; we'll throw a single clear error message
  }

  // If we reach here, no supported crypto API was found
  throw new Error(
    "No suitable crypto implementation found for SHA-256. " +
      "This function requires the Web Crypto API (crypto.subtle) in browsers or the Node 'crypto' module."
  );
}

/**
 * Convert an ArrayBuffer (or view) to a hex string.
 */
function bufferToHex(ab: ArrayBuffer): string {
  const bytes = new Uint8Array(ab);
  // map + join is fine for moderate-size inputs (SHA-256 is small)
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Convert an ArrayBuffer to base64 string (browser-safe).
 * Uses chunking to avoid call stack / argument length issues on some engines.
 */
function bufferToBase64(ab: ArrayBuffer): string {
  const bytes = new Uint8Array(ab);
  const chunkSize = 0x8000; // 32KB chunks
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const slice = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode.apply(null, Array.from(slice));
  }
  // btoa works on binary string in browsers; in Node, global btoa may not exist.
  if (typeof btoa === "function") {
    return btoa(binary);
  }
  // Node fallback
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const nodeBuffer = Buffer.from(bytes);
    return nodeBuffer.toString("base64");
  } catch (e) {
    throw new Error("Unable to convert ArrayBuffer to base64: no btoa and no Buffer available.");
  }
}

/**
 * Compute SHA-256 and return hex string.
 */
export async function sha256Hex(input: string): Promise<string> {
  const ab = await sha256ArrayBuffer(input);
  return bufferToHex(ab);
}

/**
 * Compute SHA-256 and return base64 string.
 */
export async function sha256Base64(input: string): Promise<string> {
  const ab = await sha256ArrayBuffer(input);
  return bufferToBase64(ab);
}

/**
 * Synchronous SHA-256 hex helper.
 * Only works when a synchronous provider (Node's `crypto.createHash`) is available.
 * Throws if not available.
 */
export function sha256HexSync(input: string): string {
  // Try Node's crypto synchronously
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const nodeCrypto = (typeof require !== "undefined") ? require("crypto") : null;
    if (nodeCrypto && typeof nodeCrypto.createHash === "function") {
      return nodeCrypto.createHash("sha256").update(input).digest("hex");
    }
  } catch (e) {
    // ignore and throw below
  }
  throw new Error("Synchronous SHA-256 is not available in this environment. Use sha256Hex (async) instead.");
}
