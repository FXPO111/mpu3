"use client";

import { usePathname, useSearchParams } from "next/navigation";

type DashboardView = "overview" | "prep" | "exam" | "dossier";

function toView(v: string | null): DashboardView {
  if (v === "route") return "prep";
  if (v === "evidence" || v === "documents") return "overview";
  if (v === "overview" || v === "prep" || v === "exam" || v === "dossier") return v;
  return "overview";
}

export default function CabinetHeaderNav() {
  const pathname = usePathname() || "";
  const params = useSearchParams();
  const inDashboard = pathname.startsWith("/dashboard");
  const active: DashboardView | null = inDashboard ? toView(params.get("view")) : null;

  return (
    <nav className="cabinet-v2-nav cabinet-v2-header-nav" aria-label="Навигация кабинета">
      <a className={`navlink ${active === "overview" ? "active" : ""}`} href="/dashboard?view=overview">
        Обзор
      </a>
      <a className={`navlink ${active === "prep" ? "active" : ""}`} href="/dashboard?view=prep">
        Подготовка
      </a>
      <a className={`navlink ${active === "exam" ? "active" : ""}`} href="/dashboard?view=exam">
        Экзамен
      </a>
      <a className={`navlink ${active === "dossier" ? "active" : ""}`} href="/dashboard?view=dossier">
        Досье
      </a>
    </nav>
  );
}