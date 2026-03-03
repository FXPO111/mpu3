import { NextRequest } from "next/server";
import { proxyAuthGet } from "../../../shared";
export async function GET(request: NextRequest) { return proxyAuthGet(request, "/api/payments/status"); }