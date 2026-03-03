export function resolvePublicApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");
  return configured || "";
}

export function toPublicApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const base = resolvePublicApiBase();
  return base ? `${base}${normalizedPath}` : normalizedPath;
}