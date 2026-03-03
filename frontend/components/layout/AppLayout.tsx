"use client";

import { useEffect, useState } from "react";

export default function AccountMenu({ compact = false }: { compact?: boolean }) {
  const [me, setMe] = useState<{ email: string } | null>(null);

  useEffect(() => {
    fetch("/api/client/me", { cache: "no-store" }).then(async (res) => {
      if (!res.ok) return;
      const json = await res.json();
      setMe(json?.data ?? null);
    });
  }, []);

  const logout = async () => {
    await fetch("/api/client/logout", { method: "POST" });
    window.location.href = "/";
  };

  if (!me) return <a className="cabinet-v2-menu-link" href="/pricing">Войти</a>;

  if (compact) {
    return <span className="cabinet-v2-email">{me.email}</span>;
  }

  return (
    <div className="cabinet-v2-menu">
      <span className="cabinet-v2-email">{me.email}</span>
      <a className="cabinet-v2-menu-link" href="/dashboard">Кабинет</a>
      <a className="cabinet-v2-menu-link" href="/">Главная</a>
      <button className="cabinet-v2-menu-link" onClick={logout}>Выйти</button>
    </div>
  );
}