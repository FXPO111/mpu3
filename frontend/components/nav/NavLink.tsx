"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { cn } from "../ui/cn";

function normalizeHref(href: string): { path: string; view: string | null } {
  const [pathPart, queryPart] = href.split("?");
  const params = new URLSearchParams(queryPart || "");
  return { path: pathPart || "/", view: params.get("view") };
}

export function NavLink({
  href,
  children,
  exact,
  className,
}: {
  href: string;
  children: React.ReactNode;
  exact?: boolean;
  className?: string;
}) {
  const pathname = usePathname() || "/";
  const search = useSearchParams();
  const { path, view } = normalizeHref(href);

  const pathActive = exact ? pathname === path : pathname === path || pathname.startsWith(path + "/");
  const viewActive = view ? search.get("view") === view : true;
  const active = pathActive && viewActive;

  return (
    <Link href={href} className={cn("navlink", active && "active", className)}>
      {children}
    </Link>
  );
}