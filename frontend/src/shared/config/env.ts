/**
 * Centralized frontend environment configuration.
 * Exposes strictly typed, validated configuration variables.
 */

interface EnvConfig {
  readonly apiBaseUrl: string;
  readonly apiTimeoutMs: number;
}

function parseEnv(): EnvConfig {
  const rawBaseUrl = import.meta.env.VITE_API_BASE_URL;
  const rawTimeout = import.meta.env.VITE_API_TIMEOUT_MS;

  const apiBaseUrl =
    typeof rawBaseUrl === 'string' && rawBaseUrl.trim() !== ''
      ? rawBaseUrl.trim().replace(/\/+$/, '')
      : 'http://127.0.0.1:8000';

  let apiTimeoutMs = 10000;
  if (typeof rawTimeout === 'string' && rawTimeout.trim() !== '') {
    const parsed = Number(rawTimeout);
    if (!Number.isNaN(parsed) && parsed > 0) {
      apiTimeoutMs = parsed;
    }
  }

  return Object.freeze({
    apiBaseUrl,
    apiTimeoutMs,
  });
}

export const env: EnvConfig = parseEnv();
