export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface RequestOptions extends Omit<RequestInit, 'method' | 'body'> {
  method?: HttpMethod;
  params?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  timeoutMs?: number;
}

export interface ApiErrorPayload {
  message?: string;
  detail?: string | Array<{ msg?: string; loc?: string[] }>;
  [key: string]: unknown;
}
