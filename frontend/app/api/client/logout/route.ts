import { NextResponse } from "next/server";

export async function POST() {
  const res = NextResponse.json({ data: { ok: true } });
  res.cookies.set("mpu_token", "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0 });
  return res;
}