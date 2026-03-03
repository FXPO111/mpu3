import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

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
  let payload: any;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: { message: "Invalid JSON body" } }, { status: 400 });
  }

  const email = String(payload?.email ?? "").trim();
  const password = String(payload?.password ?? "");
  const name = String(payload?.name ?? "").trim();
  if (!email || !password || !name) return NextResponse.json({ error: { message: "email/password/name required" } }, { status: 422 });

  for (const baseUrl of resolveBackendCandidates()) {
    try {
      const registerResp = await fetchWithTimeout(
        `${baseUrl}/api/auth/register`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password, name }), cache: "no-store" },
        FETCH_TIMEOUT_MS,
      );

      if (isRetryableStatus(registerResp.status)) continue;
      setLastOkBaseUrl(baseUrl);

      const registerText = await registerResp.text();
      if (!registerResp.ok && registerResp.status !== 409) {
        return new NextResponse(registerText, {
          status: registerResp.status,
          headers: { "content-type": registerResp.headers.get("content-type") ?? "application/json" },
        });
      }

      const loginResp = await fetchWithTimeout(
        `${baseUrl}/api/auth/login`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }), cache: "no-store" },
        FETCH_TIMEOUT_MS,
      );

      if (isRetryableStatus(loginResp.status)) continue;
      setLastOkBaseUrl(baseUrl);

      const loginText = await loginResp.text();
      if (!loginResp.ok) {
        return new NextResponse(loginText, {
          status: loginResp.status,
          headers: { "content-type": loginResp.headers.get("content-type") ?? "application/json" },
        });
      }

      let json: any;
      try {
        json = JSON.parse(loginText);
      } catch {
        return NextResponse.json({ error: { message: "Invalid JSON from backend" } }, { status: 502 });
      }

      const token = json?.data?.access_token;
      const res = NextResponse.json({ data: { ok: true } });
      res.cookies.set("mpu_token", String(token), { httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/" });
      return res;
    } catch {
      // try next
    }
  }

  return NextResponse.json({ error: { message: "Backend unavailable" } }, { status: 502 });
}