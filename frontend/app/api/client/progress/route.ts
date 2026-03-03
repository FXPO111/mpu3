import { NextRequest } from "next/server";
import { proxyAuthGet, proxyAuthPut } from "../../shared";

export async function GET(request: NextRequest) {
  return proxyAuthGet(request, "/api/client/progress");
}

export async function PUT(request: NextRequest) {
  return proxyAuthPut(request, "/api/client/progress");
}

// на всякий
export async function POST(request: NextRequest) {
  return proxyAuthPut(request, "/api/client/progress");
}