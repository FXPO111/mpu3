import { NextRequest, NextResponse } from "next/server";

const FETCH_TIMEOUT_MS = 2500;

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
  const normalize = (value: string) => value.trim().replace(/\/$/, "");

  const envBaseRaw = process.env.BACKEND_API_BASE_URL?.trim();
  if (envBaseRaw) return [normalize(envBaseRaw)];

  const unique = new Set<string>();
  const add = (value?: string) => {
    const normalized = value?.trim().replace(/\/$/, "");
    if (normalized) unique.add(normalized);
  };

  const lastOk = getLastOkBaseUrl();
  if (lastOk) add(lastOk);

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

export async function proxyAuthGet(request: NextRequest, backendPath: string) {
  const token = request.cookies.get("mpu_token")?.value;
  if (!token) return NextResponse.json({ data: null }, { status: 200 });

  for (const baseUrl of resolveBackendCandidates()) {
    try {
      const resp = await fetchWithTimeout(
        `${baseUrl}${backendPath}`,
        { method: "GET", headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
        FETCH_TIMEOUT_MS,
      );
      if (isRetryableStatus(resp.status)) continue;
      setLastOkBaseUrl(baseUrl);
      return new NextResponse(await resp.text(), {
        status: resp.status,
        headers: {
            "content-type": resp.headers.get("content-type") ?? "application/json",
            "x-proxy-base-url": baseUrl,
        },
      });
    } catch {
      // try next
    }
  }

  return NextResponse.json({ error: { message: "Backend unavailable" } }, { status: 502 });
}

export async function proxyAuthPost(request: NextRequest, backendPath: string) {
  const token = request.cookies.get("mpu_token")?.value;
  if (!token) return NextResponse.json({ error: { message: "Not logged in" } }, { status: 401 });
  const payload = await request.json();

  for (const baseUrl of resolveBackendCandidates()) {
    try {
      const resp = await fetchWithTimeout(
        `${baseUrl}${backendPath}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          cache: "no-store",
        },
        FETCH_TIMEOUT_MS,
      );
      if (isRetryableStatus(resp.status)) continue;
      setLastOkBaseUrl(baseUrl);
      return new NextResponse(await resp.text(), {
        status: resp.status,
        headers: {
            "content-type": resp.headers.get("content-type") ?? "application/json",
            "x-proxy-base-url": baseUrl,
        },
      });
    } catch {
      // try next
    }
  }

  return NextResponse.json({ error: { message: "Backend unavailable" } }, { status: 502 });
}

export async function proxyAuthPut(request: NextRequest, backendPath: string) {
  const token = request.cookies.get("mpu_token")?.value;
  if (!token) return NextResponse.json({ error: { message: "Not logged in" } }, { status: 401 });

  const payload = await request.json();

  for (const baseUrl of resolveBackendCandidates()) {
    try {
      const resp = await fetchWithTimeout(
        `${baseUrl}${backendPath}`,
        {
          method: "PUT",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          cache: "no-store",
        },
        FETCH_TIMEOUT_MS,
      );
      if (isRetryableStatus(resp.status)) continue;
      setLastOkBaseUrl(baseUrl);
      return new NextResponse(await resp.text(), {
        status: resp.status,
        headers: {
          "content-type": resp.headers.get("content-type") ?? "application/json",
          "x-proxy-base-url": baseUrl,
        },
      });
    } catch {
      // try next
    }
  }

  return NextResponse.json({ error: { message: "Backend unavailable" } }, { status: 502 });
}

export async function proxyPublicGet(backendPath: string) {
  for (const baseUrl of resolveBackendCandidates()) {
    try {
      const resp = await fetchWithTimeout(`${baseUrl}${backendPath}`, { method: "GET", cache: "no-store" }, FETCH_TIMEOUT_MS);
      if (isRetryableStatus(resp.status)) continue;
      setLastOkBaseUrl(baseUrl);
      return new NextResponse(await resp.text(), {
        status: resp.status,
        headers: {
            "content-type": resp.headers.get("content-type") ?? "application/json",
            "x-proxy-base-url": baseUrl,
        },
      });
    } catch {
      // try next
    }
  }
  return NextResponse.json({ error: { message: "Backend unavailable" } }, { status: 502 });
}

