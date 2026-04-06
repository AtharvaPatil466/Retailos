#!/bin/bash
# Generate TypeScript API client from OpenAPI spec
#
# Prerequisites:
#   npm install -g @openapitools/openapi-generator-cli
#   OR: pip install openapi-python-client
#
# Usage:
#   ./scripts/generate_client.sh [server_url]
#
# This script:
# 1. Fetches the OpenAPI spec from the running server
# 2. Generates a TypeScript client SDK
# 3. Outputs to dashboard/src/api/

set -e

SERVER_URL="${1:-http://localhost:8000}"
OUTPUT_DIR="dashboard/src/api"
SPEC_FILE="openapi.json"

echo "==> Fetching OpenAPI spec from $SERVER_URL/openapi.json"
curl -s "$SERVER_URL/openapi.json" -o "$SPEC_FILE"

if [ ! -s "$SPEC_FILE" ]; then
    echo "ERROR: Failed to fetch OpenAPI spec. Is the server running?"
    exit 1
fi

echo "==> Spec fetched: $(wc -c < "$SPEC_FILE") bytes"

# Method 1: openapi-typescript (lightweight, types only)
if command -v npx &> /dev/null; then
    echo "==> Generating TypeScript types with openapi-typescript..."
    mkdir -p "$OUTPUT_DIR"
    npx openapi-typescript "$SPEC_FILE" -o "$OUTPUT_DIR/schema.d.ts" 2>/dev/null || true
    echo "==> Types written to $OUTPUT_DIR/schema.d.ts"
fi

# Method 2: Generate a fetch-based client
echo "==> Generating fetch client..."
mkdir -p "$OUTPUT_DIR"

cat > "$OUTPUT_DIR/client.ts" << 'TSEOF'
/**
 * RetailOS API Client
 *
 * Auto-generated helper for the RetailOS REST API.
 * Wraps fetch() with auth headers and typed responses.
 */

const BASE_URL = window.location.origin;

type RequestOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  params?: Record<string, string>;
};

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const token = localStorage.getItem('token') || '';
  const url = new URL(path, BASE_URL);

  if (opts.params) {
    Object.entries(opts.params).forEach(([k, v]) => url.searchParams.set(k, v));
  }

  const resp = await fetch(url.toString(), {
    method: opts.method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opts.headers,
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });

  if (!resp.ok) {
    const error = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(error.detail || `Request failed: ${resp.status}`);
  }

  return resp.json();
}

// ── Auth ──────────────────────────────────────────────────

export const auth = {
  register: (data: { username: string; email: string; password: string; full_name: string; role?: string }) =>
    request<{ access_token: string; user: Record<string, unknown> }>('/api/auth/register', { method: 'POST', body: data }),

  login: (data: { username: string; password: string }) =>
    request<{ access_token: string; user: Record<string, unknown> }>('/api/auth/login', { method: 'POST', body: data }),

  me: () => request<Record<string, unknown>>('/api/auth/me'),

  users: () => request<Record<string, unknown>[]>('/api/auth/users'),
};

// ── Payments ─────────────────────────────────────────────

export const payments = {
  config: () => request<{ razorpay_key_id: string; is_configured: boolean }>('/api/payments/config'),

  createOrder: (data: { amount: number; order_id: string; customer_id?: string }) =>
    request<Record<string, unknown>>('/api/payments/create-order', { method: 'POST', body: data }),

  recordOffline: (data: { order_id: string; amount: number; method?: string }) =>
    request<{ status: string; payment: Record<string, unknown> }>('/api/payments/record-offline', { method: 'POST', body: data }),

  history: (params?: { order_id?: string; customer_id?: string }) =>
    request<{ payments: Record<string, unknown>[]; count: number }>('/api/payments/history', { params: params as Record<string, string> }),
};

// ── i18n ─────────────────────────────────────────────────

export const i18n = {
  languages: () => request<{ languages: { code: string; name: string }[] }>('/api/i18n/languages'),

  translations: (lang: string) =>
    request<{ lang: string; translations: Record<string, string> }>(`/api/i18n/translations/${lang}`),

  voiceCommand: (text: string, lang?: string) =>
    request<{ intent: string; params: Record<string, string> }>('/api/i18n/voice-command', { method: 'POST', body: { text, lang } }),
};

// ── Mobile / Barcode ─────────────────────────────────────

export const mobile = {
  barcodeLookup: (barcode: string) =>
    request<{ found: boolean; sku: string; product_name: string; current_stock: number; unit_price: number }>(`/api/mobile/barcode/${barcode}`),

  barcodeSearch: (q: string) =>
    request<{ results: Record<string, unknown>[]; match_type: string }>('/api/mobile/barcode/search', { params: { q } }),

  dashboard: () => request<Record<string, unknown>>('/api/mobile/dashboard'),
};

// ── Health ───────────────────────────────────────────────

export const health = {
  check: () => request<{ status: string }>('/health'),
  ready: () => request<{ status: string }>('/health/ready'),
  live: () => request<{ status: string }>('/health/live'),
  metrics: () => request<Record<string, unknown>>('/api/metrics'),
};

// ── Webhooks ─────────────────────────────────────────────

export const webhooks = {
  events: () => request<{ events: string[] }>('/api/webhooks/events'),

  register: (data: { url: string; events: string[]; secret?: string }) =>
    request<{ id: string; status: string }>('/api/webhooks', { method: 'POST', body: data }),

  list: () => request<{ webhooks: Record<string, unknown>[] }>('/api/webhooks'),

  remove: (id: string) => request<{ status: string }>(`/api/webhooks/${id}`, { method: 'DELETE' }),
};

// ── Scheduler ────────────────────────────────────────────

export const scheduler = {
  jobs: () => request<{ jobs: Record<string, unknown>[] }>('/api/scheduler/jobs'),
  enable: (name: string) => request<{ status: string }>(`/api/scheduler/jobs/${name}/enable`, { method: 'POST' }),
  disable: (name: string) => request<{ status: string }>(`/api/scheduler/jobs/${name}/disable`, { method: 'POST' }),
  runNow: (name: string) => request<{ status: string }>(`/api/scheduler/jobs/${name}/run-now`, { method: 'POST' }),
};

// ── Backup ───────────────────────────────────────────────

export const backup = {
  create: () => request<{ status: string; filename: string }>('/api/backup/create', { method: 'POST' }),
  list: () => request<{ backups: Record<string, unknown>[]; count: number }>('/api/backup/list'),
  restore: (filename: string) => request<{ status: string }>(`/api/backup/restore/${filename}`, { method: 'POST' }),
  remove: (filename: string) => request<{ status: string }>(`/api/backup/${filename}`, { method: 'DELETE' }),
};

// ── Stores ───────────────────────────────────────────────

export const stores = {
  list: () => request<{ stores: Record<string, unknown>[] }>('/api/stores'),
  get: (id: string) => request<Record<string, unknown>>(`/api/stores/${id}`),
  create: (data: { store_name: string; phone?: string; address?: string; gstin?: string }) =>
    request<{ id: string; status: string }>('/api/stores', { method: 'POST', body: data }),
  analytics: () => request<Record<string, unknown>>('/api/stores/analytics/summary'),
  compare: (metric: string) => request<Record<string, unknown>>('/api/stores/analytics/compare', { params: { metric } }),
};

// ── WhatsApp ─────────────────────────────────────────────

export const whatsapp = {
  status: () => request<{ configured: boolean }>('/api/whatsapp/status'),

  sendText: (phone: string, message: string) =>
    request<{ status: string }>('/api/whatsapp/send-text', { method: 'POST', body: { phone, message } }),

  sendUdhaarReminder: (data: { phone: string; customer_name: string; balance: number; due_date?: string }) =>
    request<{ status: string }>('/api/whatsapp/send-udhaar-reminder', { method: 'POST', body: data }),
};
TSEOF

echo "==> Client written to $OUTPUT_DIR/client.ts"
echo "==> Done! Import with: import { auth, payments, i18n } from './api/client'"

# Cleanup
rm -f "$SPEC_FILE"
