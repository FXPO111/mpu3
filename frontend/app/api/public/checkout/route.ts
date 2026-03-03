import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const FETCH_TIMEOUT_MS = 6000;

declare global {
  // eslint-disable-next-line no-var
  var __mpu_last_backend_base_url: string | undefined;
}

function getLastOkBaseUrl(): string | undefined {
  return globalThis.__mpu_last_backend_base_url;
}

function setLastOkBaseUrl(value: string) {
  globalThis.__mpu_last_backend_base_url = value;
}

function resolveBackendCandidates(): string[] {
  const unique = new Set<string>();
  const add = (value?: string) => {
    const normalized = value?.trim().replace(/\/$/, "");
    if (normalized) unique.add(normalized);
  };

  const envBase = process.env.BACKEND_API_BASE_URL?.trim();
  const lastOk = getLastOkBaseUrl();

  if (envBase) add(envBase);
  else if (lastOk) add(lastOk);

  add("http://backend:8000");
  add("http://host.docker.internal:8000");
  add("http://127.0.0.1:8000");
  add("http://localhost:8000");

  return Array.from(unique);
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

function isRetryableStatus(status: number): boolean {
  return status === 404 || status === 405 || status === 502 || status === 503 || status === 504;
}

export async function POST(request: NextRequest) {
  const backendCandidates = resolveBackendCandidates();

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: { message: "Invalid JSON body" } }, { status: 400 });
  }

  let lastFailedBaseUrl: string | null = null;

  for (const baseUrl of backendCandidates) {
    try {
      const response = await fetchWithTimeout(
        `${baseUrl}/api/public/checkout`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), cache: "no-store" },
        FETCH_TIMEOUT_MS,
      );

      if (isRetryableStatus(response.status)) {
        lastFailedBaseUrl = baseUrl;
        continue;
      }

      setLastOkBaseUrl(baseUrl);

      const bodyText = await response.text();
      return new NextResponse(bodyText, {
        status: response.status,
        headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
      });
    } catch {
      lastFailedBaseUrl = baseUrl;
    }
  }

  return NextResponse.json(
    { error: { message: "Backend unavailable", details: { attempted_backend_base_urls: backendCandidates, last_failed_backend_base_url: lastFailedBaseUrl } } },
    { status: 502 },
  );
}