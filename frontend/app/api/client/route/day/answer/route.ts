import { NextRequest } from "next/server";
import { proxyAuthPost } from "../../../../shared";
export async function POST(request: NextRequest) { return proxyAuthPost(request, "/api/route/day/answer"); }