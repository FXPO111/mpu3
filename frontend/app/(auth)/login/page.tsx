"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const sp = useSearchParams();

  const [email, setEmail] = useState("");
  const [pass, setPass] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const next = sp?.get("next") || "/dashboard";

  const login = async () => {
    const e = email.trim();
    if (!e || !pass) {
      setErr("Заполните email и пароль.");
      return;
    }
    setErr(null);
    setBusy(true);
    try {
      const res = await fetch("/api/client/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ email: e, password: pass }),
      });
      if (!res.ok) {
        const t = await res.text().catch(() => "");
        setErr(t || "Login failed");
        return;
      }
      router.replace(next);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="public-design-refactor" style={{ minHeight: "100vh" }}>
      <div className="modal-overlay" data-modal-overlay="true" role="dialog" aria-modal="true">
        <div className="modal-content" data-modal-content="true">
          <div className="modal-header">
            <div>
              <h1 className="modal-title">Вход</h1>
              <p className="p">Доступ в кабинет и истории кейсов.</p>
            </div>
            <a className="modal-close modal-close-icon" href="/" aria-label="Закрыть" title="Закрыть">
              <span aria-hidden="true">✕</span>
            </a>
          </div>

          <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
            <label className="label">Email</label>
            <input
              className="input"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />

            <label className="label" style={{ marginTop: 6 }}>
              Пароль
            </label>
            <input
              className="input"
              placeholder="Минимум 10 символов"
              type="password"
              value={pass}
              onChange={(e) => setPass(e.target.value)}
              autoComplete="current-password"
              onKeyDown={(e) => {
                if (e.key === "Enter") login();
              }}
            />

            {err ? (
              <div className="p" style={{ color: "var(--danger)", marginTop: 4 }}>
                {err}
              </div>
            ) : null}

            <div className="btn-group" style={{ display: "flex" }}>
              <button className="btn btn-primary" onClick={login} disabled={busy}>
                Войти
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}