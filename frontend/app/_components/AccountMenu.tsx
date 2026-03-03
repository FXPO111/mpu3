"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { usePathname } from "next/navigation";

type PlanKey = "start" | "pro" | "intensive";
type PayStatus = { program_active: boolean; plan: PlanKey | null; program_valid_to?: string | null };

const AUTH_BUMP_KEY = "mpu_auth_bump_v1";
const AUTH_EVENT_NAME = "mpu:auth-changed";

function UserIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M12 12a4.25 4.25 0 1 0-4.25-4.25A4.26 4.26 0 0 0 12 12Zm0 2c-4.42 0-8 2.24-8 5v1h16v-1c0-2.76-3.58-5-8-5Z"
      />
    </svg>
  );
}

function normalizePlan(value: any): PlanKey | null {
  if (value === "start" || value === "pro" || value === "intensive") return value;
  return null;
}

function planLabel(plan: PlanKey | null, active: boolean): string {
  if (!active || !plan) return "FREE";
  if (plan === "start") return "START";
  if (plan === "pro") return "PRO";
  return "INTENSIVE";
}

function planPillClass(plan: PlanKey | null, active: boolean, prefix: "public" | "cabinet") {
  const base = prefix === "public" ? "public-plan-pill" : "cabinet-plan-pill";
  if (!active || !plan) return `${base} ${base}--free`;
  return `${base} ${base}--${plan}`;
}

export default function AccountMenu({
  compact = false,
  publicMode = false,
}: {
  compact?: boolean;
  publicMode?: boolean;
}) {
  const [me, setMe] = useState<{ email: string } | null>(null);
  const [payStatus, setPayStatus] = useState<PayStatus | null>(null);

  // account dropdown (when logged-in in public header)
  const [menuOpen, setMenuOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  // login modal (when guest in public header)
  const [loginOpen, setLoginOpen] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPass, setLoginPass] = useState("");
  const [loginErr, setLoginErr] = useState<string | null>(null);
  const [loginBusy, setLoginBusy] = useState(false);

  // hints
  const [hintOpen, setHintOpen] = useState(false);
  const hintTimerRef = useRef<number | null>(null);

  const pathname = usePathname();
  const inCabinet = (pathname ?? "").startsWith("/dashboard");
  const effectivePublicMode = publicMode || inCabinet;
  const primaryHref = inCabinet ? "/" : "/dashboard";
  const primaryLabel = inCabinet ? "Главная" : "Кабинет";

  const pillText = useMemo(() => {
    return planLabel(payStatus?.plan ?? null, Boolean(payStatus?.program_active));
  }, [payStatus]);

  const publicPillCls = useMemo(() => {
    return planPillClass(payStatus?.plan ?? null, Boolean(payStatus?.program_active), "public");
  }, [payStatus]);

  const cabinetPillCls = useMemo(() => {
    return planPillClass(payStatus?.plan ?? null, Boolean(payStatus?.program_active), "cabinet");
  }, [payStatus]);

  const clearHintTimer = () => {
    if (hintTimerRef.current) {
      window.clearTimeout(hintTimerRef.current);
      hintTimerRef.current = null;
    }
  };

  const closeHint = (kind: "after_login" | "cabinet_home") => {
    clearHintTimer();
    setHintOpen(false);
    try {
      if (kind === "after_login") sessionStorage.removeItem("mpu_hint_after_login");
      if (kind === "cabinet_home") sessionStorage.setItem("mpu_hint_cabinet_home_v1", "1");
    } catch {}
  };

  const maybeOpenHint = () => {
    try {
      if (!me) return;

      // 1) после входа на паблике: показать "Кабинет" (или "Главная" если уже в кабинете)
      const afterLogin = sessionStorage.getItem("mpu_hint_after_login") === "1";
      if (afterLogin && !inCabinet) {
        setHintOpen(true);
        clearHintTimer();
        hintTimerRef.current = window.setTimeout(() => closeHint("after_login"), 3000);
        return;
      }

      // 2) в кабинете: один раз показать "На главную"
      if (inCabinet) {
        const seenCabinet = sessionStorage.getItem("mpu_hint_cabinet_home_v1") === "1";
        if (!seenCabinet) {
          setHintOpen(true);
          clearHintTimer();
          hintTimerRef.current = window.setTimeout(() => closeHint("cabinet_home"), 3000);
        }
      }
    } catch {}
  };

  useEffect(() => {
    fetch("/api/client/me", { cache: "no-store" }).then(async (res) => {
      if (!res.ok) return;
      const json = await res.json().catch(() => null);
      setMe(json?.data ?? null);
    });
  }, []);

  useEffect(() => {
    const refresh = () => {
      fetch("/api/client/me", { cache: "no-store" }).then(async (res) => {
        if (!res.ok) {
          setMe(null);
          return;
        }
        const json = await res.json().catch(() => null);
        setMe(json?.data ?? null);
      });
    };

    const onAuthChanged = () => refresh();
    const onStorage = (e: StorageEvent) => {
      if (e.key === AUTH_BUMP_KEY) refresh();
    };
    const onFocus = () => refresh();
    const onVis = () => {
      if (!document.hidden) refresh();
    };

    window.addEventListener(AUTH_EVENT_NAME, onAuthChanged as EventListener);
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);

    return () => {
      window.removeEventListener(AUTH_EVENT_NAME, onAuthChanged as EventListener);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  useEffect(() => {
    if (!me) {
      setPayStatus(null);
      return;
    }
    fetch("/api/client/payments/status", { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) return;
        const json = await res.json().catch(() => null);
        const data = json?.data;
        setPayStatus({
          program_active: Boolean(data?.program_active),
          plan: normalizePlan(data?.plan),
          program_valid_to: data?.program_valid_to ?? null,
        });
      })
      .catch(() => null);
  }, [me?.email]);

  useEffect(() => {
    if (!me) return;
    maybeOpenHint();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.email, inCabinet]);

  useEffect(() => {
    if (!menuOpen) return;

    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };

    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!loginOpen) return;
    document.body.classList.add("modal-open");

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeLogin();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.classList.remove("modal-open");
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loginOpen]);

  useEffect(() => {
    return () => {
      clearHintTimer();
    };
  }, []);

  const logout = async () => {
    await fetch("/api/client/logout", { method: "POST" }).catch(() => null);
    try {
      sessionStorage.removeItem("mpu_hint_after_login");
      sessionStorage.removeItem("mpu_hint_cabinet_home_v1");
    } catch {}
    window.location.href = "/";
  };

  const closeLogin = () => {
    setLoginOpen(false);
    setLoginErr(null);
  };

  const doLogin = async () => {
    const email = loginEmail.trim();
    if (!email || !loginPass) {
      setLoginErr("Заполните email и пароль.");
      return;
    }
    setLoginErr(null);
    setLoginBusy(true);
    try {
      const res = await fetch("/api/client/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ email, password: loginPass }),
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        setLoginErr(t || "Ошибка входа.");
        return;
      }

      // показать подсказку “Кабинет” после входа
      try {
        sessionStorage.setItem("mpu_hint_after_login", "1");
      } catch {}

      const meRes = await fetch("/api/client/me", { cache: "no-store" });
      if (meRes.ok) {
        const json = await meRes.json().catch(() => null);
        setMe(json?.data ?? null);
      }

      closeLogin();
    } finally {
      setLoginBusy(false);
    }
  };

  // ---- GUEST ----
  if (!me) {
    if (!effectivePublicMode) return <a className="cabinet-v2-menu-link" href="/login">Войти</a>;

    const modal =
      loginOpen && typeof document !== "undefined"
        ? createPortal(
            <div
              className="modal-overlay auth-login-modal"
              data-modal-overlay="true"
              role="dialog"
              aria-modal="true"
              onMouseDown={(e) => {
                if (e.currentTarget === e.target) closeLogin();
              }}
            >
              <div
                className="modal-content auth-login-card"
                data-modal-content="true"
                onMouseDown={(e) => e.stopPropagation()}
              >
                <div className="modal-header">
                  <div>
                    <h2 className="modal-title">Вход</h2>
                    <p className="p">Доступ в кабинет и истории кейсов.</p>
                  </div>
                  <button
                    type="button"
                    className="modal-close modal-close-icon"
                    onClick={closeLogin}
                    aria-label="Закрыть"
                  >
                    <span aria-hidden="true">✕</span>
                  </button>
                </div>

                <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
                  <label className="label">Email</label>
                  <input
                    className="input"
                    placeholder="you@example.com"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    autoComplete="email"
                  />

                  <label className="label" style={{ marginTop: 6 }}>
                    Пароль
                  </label>
                  <input
                    className="input"
                    placeholder="Минимум 10 символов"
                    type="password"
                    value={loginPass}
                    onChange={(e) => setLoginPass(e.target.value)}
                    autoComplete="current-password"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") doLogin();
                    }}
                  />

                  {loginErr ? (
                    <div className="p" style={{ color: "var(--danger)", marginTop: 4 }}>
                      {loginErr}
                    </div>
                  ) : null}

                  <div className="btn-group" style={{ display: "flex" }}>
                    <button className="btn btn-primary" onClick={doLogin} disabled={loginBusy}>
                      Войти
                    </button>
                  </div>
                </div>
              </div>
            </div>,
            document.body
          )
        : null;

    return (
      <>
        <button type="button" className="public-account-login" onClick={() => setLoginOpen(true)}>
          Войти
        </button>
        {modal}
      </>
    );
  }

  // ---- LOGGED-IN ----
    if (compact && !effectivePublicMode) {
    return (
      <div className="cabinet-v2-menu" style={{ position: "relative" }}>
        <span className="cabinet-v2-email">{me.email}</span>
        <span className={cabinetPillCls} title="Текущий тариф">
          {pillText}
        </span>

        {hintOpen && inCabinet ? (
          <div className="hint-bubble hint-bubble--cabinet" role="status" aria-live="polite">
            <div className="hint-bubble-text">На главную — нажмите здесь.</div>
            <button
              className="hint-bubble-close"
              type="button"
              onClick={() => closeHint("cabinet_home")}
              aria-label="Закрыть"
            >
              ✕
            </button>
          </div>
        ) : null}

        <a className="cabinet-v2-menu-link" href={primaryHref}>
          {primaryLabel}
        </a>
        <button className="cabinet-v2-menu-link" onClick={logout}>
          Выйти
        </button>
      </div>
    );
  }

  if (effectivePublicMode) {
    const hintKind: "after_login" | "cabinet_home" = inCabinet ? "cabinet_home" : "after_login";
    const hintText = inCabinet
      ? "На главную, нажмите здесь."
      : "В кабинет, нажмите здесь.";

    return (
      <div
        className={`public-user${inCabinet ? " public-user--cabinet" : ""}`}
        ref={wrapRef}
        style={{ position: "relative" }}
      >
        <button type="button" className="public-user-btn" onClick={() => setMenuOpen(true)} title="Аккаунт">
          <span className="public-user-dot" />
          <UserIcon />
          <span className={publicPillCls} title="Текущий тариф" style={{ marginLeft: 6 }}>
            {pillText}
          </span>
        </button>

        {hintOpen ? (
          <div className={`hint-bubble hint-bubble--account`} role="status" aria-live="polite">
            <div className="hint-bubble-text">{hintText}</div>
            <button className="hint-bubble-close" type="button" onClick={() => closeHint(hintKind)} aria-label="Закрыть">
              ✕
            </button>
          </div>
        ) : null}

        {menuOpen && (
          <div className="public-user-overlay" role="dialog" aria-modal="true">
            <div className="public-user-menu">
              <div className="public-user-head">
                <div className="public-user-email" title={me.email}>{me.email}</div>
                <button className="public-user-close" onClick={() => setMenuOpen(false)} type="button" aria-label="Закрыть">
                  ✕
                </button>
              </div>

              <div className="public-user-actions">
                <a className="public-user-item" href={primaryHref} onClick={() => setMenuOpen(false)}>
                  {primaryLabel}
                </a>

                <button className="public-user-item danger" onClick={logout} type="button">
                  Выйти
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // cabinet header (non public)
  return (
    <div className="cabinet-v2-menu" style={{ position: "relative" }}>
      <span className="cabinet-v2-email">{me.email}</span>
      <span className={cabinetPillCls} title="Текущий тариф">
        {pillText}
      </span>

      {hintOpen && inCabinet ? (
        <div className="hint-bubble hint-bubble--cabinet" role="status" aria-live="polite">
          <div className="hint-bubble-text">На главную, нажмите здесь.</div>
          <button className="hint-bubble-close" type="button" onClick={() => closeHint("cabinet_home")} aria-label="Закрыть">
            ✕
          </button>
        </div>
      ) : null}

      <a className="cabinet-v2-menu-link" href={primaryHref}>{primaryLabel}</a>
      <button className="cabinet-v2-menu-link" onClick={logout}>Выйти</button>
    </div>
  );
}