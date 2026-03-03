"use client";
import { useEffect, useState } from "react";

export default function PaySuccessPage() {
  const [status, setStatus] = useState("Оплата обрабатывается…");

  useEffect(() => {
    const sessionId = new URLSearchParams(window.location.search).get("session_id");
    const confirmIfPossible = async () => {
      if (!sessionId) return;
      await fetch("/api/client/payments/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ checkout_session_id: sessionId }),
      }).catch(() => null);
    };

    let tries = 0;
    void confirmIfPossible();
    const id = setInterval(async () => {
      tries += 1;
      if (tries % 3 === 0) {
        await confirmIfPossible();
      }
      const res = await fetch("/api/client/payments/status", { cache: "no-store" });
      const json = await res.json().catch(() => null);
      if (json?.data?.program_active) {
        window.location.href = "/dashboard";
        return;
      }
      if (tries >= 60) {
        clearInterval(id);
        setStatus("Статус еще не обновился.");
      }
    }, 1500);
    return () => clearInterval(id);
  }, []);

  return <main><h1>{status}</h1><a href="/dashboard">Перейти в кабинет</a></main>;
}