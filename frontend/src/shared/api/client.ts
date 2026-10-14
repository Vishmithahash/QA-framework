import { env } from '@/shared/config/env';
import type { ApiErrorPayload, RequestOptions } from '@/shared/types/api';

export class ApiClientError extends Error {
  public readonly status: number;
  public readonly statusText: string;
  public readonly url: string;
  public readonly data: ApiErrorPayload | string | null;

  constructor(
    status: number,
    statusText: string,
    url: string,
    data: ApiErrorPayload | string | null
  ) {
    const detailMsg =
      typeof data === 'object' && data !== null && 'detail' in data
        ? typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail)
        : null;

    const message = detailMsg || `Request failed with status ${status} (${statusText})`;
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.statusText = statusText;
    this.url = url;
    this.data = data;
  }
}

export interface ApiClientConfig {
  baseUrl?: string;
  apiPrefix?: string;
  defaultTimeoutMs?: number;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly apiPrefix: string;
  private readonly defaultTimeoutMs: number;

  constructor(config: ApiClientConfig = {}) {
    this.baseUrl = (config.baseUrl ?? env.apiBaseUrl).replace(/\/+$/, '');
    this.apiPrefix = (config.apiPrefix ?? '').replace(/^\/+/, '').replace(/\/+$/, '');
    this.defaultTimeoutMs = config.defaultTimeoutMs ?? env.apiTimeoutMs;
  }

  private buildUrl(
    endpoint: string,
    params?: Record<string, string | number | boolean | undefined | null>
  ): string {
    const cleanEndpoint = endpoint.replace(/^\/+/, '');
    const path = this.apiPrefix ? `${this.apiPrefix}/${cleanEndpoint}` : cleanEndpoint;
    const fullUrl = new URL(`${this.baseUrl}/${path}`);

    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          fullUrl.searchParams.append(key, String(value));
        }
      });
    }

    return fullUrl.toString();
  }

  public async request<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const {
      method = 'GET',
      params,
      body,
      headers: customHeaders,
      timeoutMs = this.defaultTimeoutMs,
      signal: externalSignal,
      ...customInit
    } = options;

    const url = this.buildUrl(endpoint, params);
    const controller = new AbortController();

    // Link external cancellation signal if provided
    let externalSignalCleanup: (() => void) | undefined;
    if (externalSignal) {
      if (externalSignal.aborted) {
        controller.abort();
      } else {
        const onAbort = () => controller.abort();
        externalSignal.addEventListener('abort', onAbort, { once: true });
        externalSignalCleanup = () => externalSignal.removeEventListener('abort', onAbort);
      }
    }

    const timeoutId = setTimeout(() => {
      controller.abort();
    }, timeoutMs);

    const headers = new Headers(customHeaders);
    let serializedBody: BodyInit | undefined;

    if (body !== undefined && body !== null) {
      if (
        typeof body === 'string' ||
        body instanceof FormData ||
        body instanceof Blob ||
        body instanceof URLSearchParams
      ) {
        serializedBody = body;
      } else {
        headers.set('Content-Type', 'application/json');
        serializedBody = JSON.stringify(body);
      }
    }

    // Default Accept header
    if (!headers.has('Accept')) {
      headers.set('Accept', 'application/json');
    }

    try {
      const response = await fetch(url, {
        ...customInit,
        method,
        headers,
        body: serializedBody,
        signal: controller.signal,
      });

      // Handle 204 No Content or empty responses gracefully
      if (response.status === 204 || response.headers.get('content-length') === '0') {
        return null as unknown as T;
      }

      const contentType = response.headers.get('content-type') || '';
      const isJson = contentType.includes('application/json');

      if (!response.ok) {
        let errorData: ApiErrorPayload | string | null = null;
        try {
          errorData = isJson ? await response.json() : await response.text();
        } catch {
          errorData = null;
        }
        throw new ApiClientError(response.status, response.statusText, url, errorData);
      }

      if (isJson) {
        return (await response.json()) as T;
      }

      return (await response.text()) as unknown as T;
    } finally {
      clearTimeout(timeoutId);
      if (externalSignalCleanup) {
        externalSignalCleanup();
      }
    }
  }

  public get<T = unknown>(endpoint: string, options?: Omit<RequestOptions, 'method'>): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  }

  public post<T = unknown>(
    endpoint: string,
    body?: unknown,
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'POST', body });
  }

  public put<T = unknown>(
    endpoint: string,
    body?: unknown,
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'PUT', body });
  }

  public patch<T = unknown>(
    endpoint: string,
    body?: unknown,
    options?: Omit<RequestOptions, 'method' | 'body'>
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'PATCH', body });
  }

  public delete<T = unknown>(
    endpoint: string,
    options?: Omit<RequestOptions, 'method'>
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }
}

// Default pre-configured singleton instance
export const apiClient = new ApiClient();
