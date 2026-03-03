import { proxyPublicGet } from "../../shared";

export async function GET() {
  return proxyPublicGet("/api/public/products");
}