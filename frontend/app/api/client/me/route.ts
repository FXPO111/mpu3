import { NextRequest } from "next/server";
import { proxyAuthGet } from "../../shared";

export async function GET(request: NextRequest) {
  return proxyAuthGet(request, "/api/auth/me");
}

// Some clients/devtools/plugins accidentally call POST/HEAD on this endpoint.
// Keep behavior graceful instead of returning 405 noise.
export async function POST(request: NextRequest) {
  return proxyAuthGet(request, "/api/auth/me");
}

export async function HEAD(request: NextRequest) {
  return proxyAuthGet(request, "/api/auth/me");
}