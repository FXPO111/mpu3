"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type Me = {
  id: string;
  email: string;
  name: string;
  locale: string;
  role: string;
  status: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type SessionMeta = {
  id: string;
  mode: "practice" | "mock" | "diagnostic";
  locale: "de" | "ru";
  status: string;
};

async function jfetch<T>(
  url: string,
  init?: RequestInit,
): Promise<{ ok: boolean; status: number; data?: T; errorText?: string }> {
  const resp = await fetch(url, { ...init, cache: "no-store" });
  const text = await resp.text();
  if (!resp.ok) return { ok: false, status: resp.status, errorText: text };
  try {
    return { ok: true, status: resp.status, data: JSON.parse(text) as T };
  } catch {
    return { ok: true, status: resp.status, data: (text as unknown) as T };
  }
}

export default function TrainerSessionPage({ params }: { params: { sessionId: string } }) {
  const router = useRouter();
  const pathname = usePathname();

  // База пути без последнего сегмента (чтобы корректно работать в любой вложенности)
  const basePath = useMemo(() => {
    const parts = (pathname || "").split("/").filter(Boolean);
    return "/" + parts.slice(0, Math.max(parts.length - 1, 0)).join("/");
  }, [pathname]);

  const sessionId = params.sessionId;

  const [me, setMe] = useState<Me | null>(null);
  const [authEmail, setAuthEmail] = useState("");
  const [authPass, setAuthPass] = useState("");
  const [authErr, setAuthErr] = useState<string | null>(null);

  const [mode, setMode] = useState<"practice" | "mock" | "diagnostic">("practice");
  const [locale, setLocale] = useState<"de" | "en">("de");

  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionMeta, setSessionMeta] = useState<SessionMeta | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement | null>(null);

  async function loadMe() {
    const r = await jfetch<{ data: Me }>("/api/client/me");
    if (!r.ok) {
      setMe(null);
      return;
    }
    setMe((r.data as any).data);
  }

  async function login() {
    setAuthErr(null);
    setBusy(true);
    try {
      const r = await jfetch<{ data: { ok: true } }>("/api/client/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: authEmail.trim(), password: authPass }),
      });

      if (!r.ok) {
        setAuthErr(r.errorText ?? "Login failed");
        return;
      }

      await loadMe();
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    try {
      await fetch("/api/client/logout", { method: "POST" });
      setMe(null);
      setMessages([]);
      setErr(null);
    } finally {
      setBusy(false);
    }
  }

  async function createSessionAndGo() {
    setErr(null);
    setBusy(true);
    try {
      const r = await jfetch<{ data: { id: string } }>("/api/client/ai/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, locale }),
      });

      if (!r.ok) {
        setErr(r.errorText ?? "Create session failed");
        return;
      }

      const id = (r.data as any).data?.id;
      if (!id) {
        setErr("No session id returned");
        return;
      }

      router.replace(`${basePath}/${id}`);
    } finally {
      setBusy(false);
    }
  }

  async function loadSessionMeta(id: string) {
    const r = await jfetch<{ data: SessionMeta }>(`/api/client/ai/sessions/${id}`, { method: "GET" });
    if (!r.ok) return;
    setSessionMeta((r.data as any).data ?? null);
  }

  async function loadMessages(id: string) {
    setErr(null);
    const r = await jfetch<{ data: Message[] }>(`/api/client/ai/sessions/${id}/messages`, { method: "GET" });
    if (!r.ok) {
      setErr(r.errorText ?? "Load messages failed");
      return;
    }
    setMessages((r.data as any).data ?? []);
  }

  async function sendContent(content: string, opts?: { clearInput?: boolean }) {
    setErr(null);
    setBusy(true);
    try {
      const r = await jfetch<any>(`/api/client/ai/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });

      if (!r.ok) {
        setErr(r.errorText ?? "Send failed");
        return false;
      }

      if (opts?.clearInput) setInput("");
      await loadMessages(sessionId);
      return true;
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    const content = input.trim();
    if (!content) return;
    await sendContent(content, { clearInput: true });
  }

  async function startTraining() {
    const modeNow = sessionMeta?.mode ?? mode;
    if (!(modeNow === "practice" || modeNow === "mock")) return;
    const boot = modeNow === "mock" ? "[[START_MOCK]]" : "[[START_PRACTICE]]";
    await sendContent(boot);
  }

  async function quickYes() {
    await sendContent("да");
  }

  useEffect(() => {
    loadMe();
  }, []);

  useEffect(() => {
    if (me && sessionId && sessionId !== "new") {
      (async () => {
        await loadSessionMeta(sessionId);
        await loadMessages(sessionId);
      })();
    }
  }, [me, sessionId]);

  useEffect(() => {
    if (!me || sessionId === "new") return;
    if (!sessionMeta) return;
    if (!(sessionMeta.mode === "practice" || sessionMeta.mode === "mock")) return;
    if (messages.length > 0) return;
    startTraining();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me, sessionId, sessionMeta, messages.length]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="card pad">
        <div className="badge">AI trainer</div>
        <h1 className="h2" style={{ marginTop: 10 }}>
          Сессия: {sessionId}
        </h1>
        <p className="p">Тестируем backend через фронт (без Swagger/Bearer вручную).</p>

        <div className="hr" />

        {!me ? (
          <div style={{ display: "grid", gap: 10, maxWidth: 520 }}>
            <div className="badge">Login</div>
            <Input placeholder="email" value={authEmail} onChange={(e) => setAuthEmail(e.target.value)} />
            <Input
              placeholder="password"
              type="password"
              value={authPass}
              onChange={(e) => setAuthPass(e.target.value)}
            />
            {authErr ? (
              <div className="p" style={{ color: "var(--danger)" }}>
                {authErr}
              </div>
            ) : null}
            <Button onClick={login} disabled={busy}>
              Войти
            </Button>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <div className="badge">{me.email}</div>
            <Button onClick={logout} disabled={busy}>
              Выйти
            </Button>

            <div style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <label className="p" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                mode
                <select value={mode} onChange={(e) => setMode(e.target.value as any)} className="input">
                  <option value="practice">practice</option>
                  <option value="mock">mock</option>
                  <option value="diagnostic">diagnostic</option>
                </select>
              </label>

              <label className="p" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                locale
                <select value={locale} onChange={(e) => setLocale(e.target.value as any)} className="input">
                  <option value="de">de</option>
                  <option value="en">en</option>
                </select>
              </label>

              <Button onClick={createSessionAndGo} disabled={busy}>
                Создать новую сессию
              </Button>
            </div>
          </div>
        )}
      </div>

      {me ? (
        <div className="card pad">
          {sessionId === "new" ? (
            <div style={{ display: "grid", gap: 10 }}>
              <div className="badge">Новая сессия</div>
              <p className="p">Жми “Создать новую сессию” сверху — перекинет на UUID.</p>
            </div>
          ) : (
            <>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <Input
                  placeholder="Напиши ответ…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                />
                <Button onClick={send} disabled={busy}>
                  Отправить
                </Button>
                <Button onClick={startTraining} disabled={busy}>
                  Начать обучение
                </Button>
                <Button onClick={quickYes} disabled={busy}>
                  Да
                </Button>
              </div>

              {err ? (
                <div className="p" style={{ marginTop: 10, color: "var(--danger)" }}>
                  {err}
                </div>
              ) : null}

              <div className="hr" />

              <div style={{ display: "grid", gap: 10 }}>
                {messages.map((m) => (
                  <div key={m.id} className="card pad" style={{ boxShadow: "none" }}>
                    <div className="badge">{m.role === "assistant" ? "Эксперт" : "Вы"}</div>
                    <p className="p" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                      {m.content}
                    </p>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}