import { md5 } from 'js-md5';

export type LoginChallenge = {
  challenge_id: string;
  nonce: string;
  algorithm: 'pbkdf2_sha256' | 'legacy_md5' | 'argon2';
  iterations?: number;
  salt?: string;
};

const encoder = new TextEncoder();

function bytesToHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

function hexToBytes(hex: string): Uint8Array {
  if (hex.length % 2 !== 0) {
    throw new Error('Invalid hex payload');
  }

  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = Number.parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}

async function signNonce(secret: BufferSource, nonce: string): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    throw new Error('Current browser does not support secure login');
  }

  const key = await subtle.importKey(
    'raw',
    secret,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await subtle.sign('HMAC', key, encoder.encode(nonce));
  return bytesToHex(signature);
}

async function createPbkdf2Proof(password: string, challenge: LoginChallenge): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle || !challenge.salt || !challenge.iterations) {
    throw new Error('Invalid secure login challenge');
  }

  const passwordKey = await subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveBits']);
  const derivedBits = await subtle.deriveBits(
    {
      name: 'PBKDF2',
      hash: 'SHA-256',
      salt: hexToBytes(challenge.salt),
      iterations: challenge.iterations
    },
    passwordKey,
    256
  );

  return signNonce(derivedBits, challenge.nonce);
}

async function createLegacyMd5Proof(password: string, challenge: LoginChallenge): Promise<string> {
  return signNonce(encoder.encode(md5(password).toLowerCase()), challenge.nonce);
}

export async function createLoginProof(password: string, challenge: LoginChallenge): Promise<string> {
  if (challenge.algorithm === 'pbkdf2_sha256') {
    return createPbkdf2Proof(password, challenge);
  }
  if (challenge.algorithm === 'legacy_md5') {
    return createLegacyMd5Proof(password, challenge);
  }
  throw new Error('Unsupported secure login algorithm');
}
