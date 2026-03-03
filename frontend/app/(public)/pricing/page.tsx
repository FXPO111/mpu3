"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

type PlanKey = "start" | "pro" | "intensive";
type Product = { id: string; code: string; price_cents: number; currency: string; type: string };

const FALLBACK_PLANS: Product[] = [
  { id: "fallback-start", code: "PLAN_START", price_cents: 23000, currency: "EUR", type: "program" },
  { id: "fallback-pro", code: "PLAN_PRO", price_cents: 70000, currency: "EUR", type: "program" },
  { id: "fallback-intensive", code: "PLAN_INTENSIVE", price_cents: 150000, currency: "EUR", type: "program" },
];

const PLAN_UI: Record<string, { key: PlanKey; title: string; days: string; bullets: string[] }> = {
  PLAN_START: {
    key: "start",
    title: "Start",
    days: "30 дней",
    bullets: [
      "Диагностика и карта рисков",
      "План подготовки по неделям",
      "Базовые модули",
      "Тренировки интервью",
      "Чеклист документов",
    ],
  },
  PLAN_PRO: {
    key: "pro",
    title: "Pro",
    days: "30 дней",
    bullets: [
      "Всё из Start",
      "Тренировки интервью без лимита",
      "Расширенная проверка формулировок",
      "Финальный контроль готовности + отчёт",
    ],
  },
  PLAN_INTENSIVE: {
    key: "intensive",
    title: "Intensive",
    days: "30 дней",
    bullets: [
      "Всё из Pro",
      "Дополнительные итерации финальной проверки",
      "Приоритетная поддержка",
    ],
  },
};

function isValidUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function planFromCode(code: string): PlanKey | null {
  if (code === "PLAN_START") return "start";
  if (code === "PLAN_PRO") return "pro";
  if (code === "PLAN_INTENSIVE") return "intensive";
  return null;
}

function formatPrice(priceCents: number, currency: string): string {
  const value = Math.round(priceCents / 100);
  if (currency === "EUR") return `€${value}`;
  return `${value} ${currency}`;
}

async function loadProductsFromAnySource(): Promise<Product[] | null> {
  const proxyResp = await fetch("/api/client/products", { cache: "no-store" }).catch(() => null);
  if (proxyResp?.ok) {
    const json = await proxyResp.json().catch(() => null);
    const rows = (json?.data ?? []) as Product[];
    const plans = rows.filter((p) => p.type === "program" && ["PLAN_START", "PLAN_PRO", "PLAN_INTENSIVE"].includes(p.code));
    if (plans.length) return plans;
  }
  return null;
}

export default function PricingPage() {
  const params = useSearchParams();
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [showAuth, setShowAuth] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [pendingProductId, setPendingProductId] = useState<string | null>(null);

  const [authForm, setAuthForm] = useState({ email: "", password: "", name: "" });
  const [authError, setAuthError] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(false);

  useEffect(() => {
    const loadProducts = async () => {
      const plans = await loadProductsFromAnySource();
      if (plans?.length) {
        setProducts(plans);
        return;
      }
      setProducts(FALLBACK_PLANS);
      setError("Не удалось обновить тарифы с сервера, показаны базовые цены.");
    };
    void loadProducts();
  }, []);

  useEffect(() => {
    const plan = params.get("plan");
    if (plan) localStorage.setItem("recommended_plan", plan);
  }, [params]);

  const sorted = useMemo(() => {
    const order = { PLAN_START: 0, PLAN_PRO: 1, PLAN_INTENSIVE: 2 } as Record<string, number>;
    return [...products].sort((a, b) => (order[a.code] ?? 99) - (order[b.code] ?? 99));
  }, [products]);

  const recommended = useMemo<PlanKey>(() => {
    const q = params.get("plan");
    if (q === "start" || q === "pro" || q === "intensive") return q;
    const ls = typeof window !== "undefined" ? localStorage.getItem("recommended_plan") : null;
    if (ls === "start" || ls === "pro" || ls === "intensive") return ls;
    return "start";
  }, [params]);

  async function runCheckout(productId: string): Promise<boolean> {
    setError(null);
    const res = await fetch("/api/client/payments/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: productId }),
    });
    const json = await res.json().catch(() => ({} as any));
    if (!res.ok) {
      if (res.status === 401) {
        setShowAuth(true);
        setAuthError("Сессия истекла, войдите снова.");
      } else {
        setError(json?.error?.message ?? "Checkout error");
      }
      return false;
    }
    if (json?.data?.checkout_url) {
      window.location.href = json.data.checkout_url;
      return true;
    }
    setError("Сервер не вернул ссылку на оплату");
    return false;
  }

  async function tryCheckoutWithRetry(productId: string, attempts = 3): Promise<boolean> {
    for (let i = 0; i < attempts; i += 1) {
      const started = await runCheckout(productId);
      if (started) return true;
      await new Promise((r) => setTimeout(r, 250));
    }
    return false;
  }

  async function resolveCheckoutProductId(productId: string): Promise<string | null> {
    if (isValidUuid(productId)) return productId;

    const current = products.find((p) => p.id === productId);
    const refreshed = await loadProductsFromAnySource();
    if (refreshed?.length) {
      setProducts(refreshed);
      const byCode = refreshed.find((p) => p.code === current?.code);
      if (byCode?.id && isValidUuid(byCode.id)) return byCode.id;
    }

    return null;
  }

  async function onBuy(productId: string) {
    const checkoutProductId = await resolveCheckoutProductId(productId);
    if (!checkoutProductId) {
      setError("Не удалось получить ID тарифа с сервера. Проверьте backend и обновите страницу.");
      return;
    }

    const started = await runCheckout(checkoutProductId);
    if (started) return;

    setPendingProductId(productId);
    setAuthError(null);
    setShowAuth(true);
  }

  async function submitAuth() {
    if (authLoading) return;

    const email = authForm.email.trim();
    const password = authForm.password.trim();
    const name = authForm.name.trim();

    if (!email || !password) return setAuthError("Введите email и пароль");
    if (password.length < 10) return setAuthError("Пароль должен быть минимум 10 символов");
    if (mode === "register" && !name) return setAuthError("Введите имя для регистрации");

    setAuthLoading(true);
    setAuthError(null);

    try {
      const path = mode === "login" ? "/api/client/login" : "/api/client/register";
      const payload = mode === "login" ? { email, password } : { email, password, name: name || email.split("@")[0] };
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const json = await res.json().catch(() => ({} as any));
        const detail = Array.isArray(json?.detail) ? json.detail[0]?.msg : null;
        if (mode === "register" && res.status === 409) {
          setMode("login");
          setAuthError("Этот email уже зарегистрирован. Войдите с паролем.");
          return;
        }
        setAuthError(json?.error?.message ?? detail ?? "Auth error");
        return;
      }

      if (pendingProductId) {
        const checkoutProductId = await resolveCheckoutProductId(pendingProductId);
        if (!checkoutProductId) {
          setError("Не удалось получить ID тарифа с сервера. Проверьте backend и обновите страницу.");
          return;
        }

        const started = await tryCheckoutWithRetry(checkoutProductId, 3);
        if (!started) {
          setAuthError("Не удалось перейти к оплате. Попробуйте ещё раз.");
          return;
        }
      }

      setShowAuth(false);
    } catch {
      setAuthError("Сетевая ошибка. Попробуйте ещё раз.");
    } finally {
      setAuthLoading(false);
    }
  }

  return (
    <div className="pricing-page-xl public-page-stack">
      <section className="section" id="pricing">
        <div className="pricing-clean-hero card pad premium-hero-compact">
          <h1 className="h1 premium-hero-title">Выберите формат подготовки</h1>
          <p className="lead mt-12 premium-hero-sub">
            Начните с диагностики — рекомендованный вариант будет отмечен автоматически.
          </p>

          {error ? (
            <div className="card pad soft mt-16">
              <div className="badge">Важно</div>
              <p className="p mt-8">{error}</p>
            </div>
          ) : null}
        </div>

        <div className="plan-grid pricing-grid-equal mt-16">
          {sorted.map((p) => {
            const ui = PLAN_UI[p.code] ?? { key: planFromCode(p.code) ?? "start", title: p.code, days: "", bullets: [] };
            const isFeatured = ui.key === recommended;

            return (
              <article
                key={p.id}
                className={[
                  "card",
                  "pad",
                  "clean-plan",
                  "pricing-plan-card",
                  "plan-card",
                  isFeatured ? "clean-plan-featured plan-card-primary" : "",
                ].join(" ")}
              >
                <div className="pricing-plan-note">
                  {isFeatured ? <span className="badge">Рекомендовано</span> : <span className="badge" style={{ opacity: 0.0 }}>.</span>}
                </div>

                <h3 className="h3">{ui.title}</h3>

                <div className="plan-price-wrap">
                  <div className="plan-price">{formatPrice(p.price_cents, p.currency)}</div>
                </div>

                {ui.days ? <div className="small mt-8">{ui.days}</div> : null}

                {ui.bullets?.length ? (
                  <ul className="plan-list mt-12">
                    {ui.bullets.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                ) : null}

                <div className="pricing-plan-actions">
                  <button
                    className={`btn btn-lg w-full ${isFeatured ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => onBuy(p.id)}
                    type="button"
                  >
                    Выбрать {ui.title} и оплатить
                  </button>
                </div>
              </article>
            );
          })}
        </div>

        <p className="small mt-16" style={{ textAlign: "center" }}>
          Результат зависит от исходных данных и выполнения программы. Подготовка снижает риск провала за счёт структуры,
          тренировок и контроля.
        </p>
      </section>

      {showAuth ? (
        <div className="modal-overlay" onClick={() => (!authLoading ? setShowAuth(false) : null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h2 className="h2">{mode === "login" ? "Вход" : "Регистрация"}</h2>
                <p className="p mt-8">
                  {mode === "login" ? "Войдите, чтобы перейти к оплате." : "Создайте аккаунт, чтобы перейти к оплате."}
                </p>
              </div>
              <button
                type="button"
                className="modal-close modal-close-icon"
                onClick={() => (!authLoading ? setShowAuth(false) : null)}
                aria-label="Закрыть"
              >
                <span aria-hidden="true">✕</span>
              </button>
            </div>

            {authError ? <p className="error mt-12">{authError}</p> : null}

            <div className="stack mt-12">
              {mode === "register" ? (
                <div className="field">
                  <div className="label">Имя</div>
                  <input
                    className="input"
                    value={authForm.name}
                    onChange={(e) => setAuthForm((s) => ({ ...s, name: e.target.value }))}
                    placeholder="Ваше имя"
                    autoComplete="name"
                  />
                </div>
              ) : null}

              <div className="field">
                <div className="label">Email</div>
                <input
                  className="input"
                  value={authForm.email}
                  onChange={(e) => setAuthForm((s) => ({ ...s, email: e.target.value }))}
                  placeholder="you@example.com"
                  autoComplete="email"
                />
              </div>

              <div className="field">
                <div className="label">Пароль</div>
                <input
                  className="input"
                  type="password"
                  value={authForm.password}
                  onChange={(e) => setAuthForm((s) => ({ ...s, password: e.target.value }))}
                  placeholder="Минимум 10 символов"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                />
              </div>

              <div className="btn-group mt-12">
                <button className="btn btn-primary btn-lg" type="button" onClick={submitAuth} disabled={authLoading}>
                  {authLoading ? "Подождите…" : mode === "login" ? "Войти" : "Зарегистрироваться"}
                </button>

                <button
                  className="btn btn-ghost btn-lg"
                  type="button"
                  onClick={() => {
                    if (authLoading) return;
                    setMode((m) => (m === "login" ? "register" : "login"));
                    setAuthError(null);
                  }}
                >
                  {mode === "login" ? "Нет аккаунта" : "Уже есть аккаунт"}
                </button>
              </div>

              <p className="small mt-12">
                Оплата откроется автоматически после успешного входа/регистрации.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}