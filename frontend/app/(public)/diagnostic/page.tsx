"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { toPublicApiUrl } from "@/lib/public-api-base";

type PlanKey = "start" | "pro" | "intensive";

const STEP_TITLES = ["Тема", "Ситуация", "История", "Цель"] as const;
const REASONS = ["Алкоголь", "Наркотики", "Пункты / штрафы", "Поведение / инцидент", "Другое"] as const;

const HELP_ITEMS = [
  {
    title: "Что оцениваем на этом шаге",
    text: "Определяем исходную причину и фокус подготовки. Это помогает сразу исключить лишние темы и собрать правильный маршрут.",
  },
  {
    title: "Как писать ответы",
    text: "Коротко и по делу: 1–3 предложения на шаг. Достаточно базовой логики без деталей, которые вы не хотите раскрывать.",
  },
  {
    title: "Что получите после заполнения",
    text: "Сформируем персональную структуру подготовки: приоритетные темы, зоны риска и рекомендации по формулировкам.",
  },
  {
    title: "Конфиденциальность и сохранение",
    text: "Черновик сохраняется автоматически в вашем браузере. Ответы используются только для подготовки и не публикуются.",
  },
] as const;

function detectPlan(payload: { reasons: string[]; situation: string; history: string; goal: string; other: string }): PlanKey {
  const text = [payload.reasons.join(" "), payload.other, payload.situation, payload.history, payload.goal].join(" ").toLowerCase();
  const intenseKeywords = ["повтор", "отказ", "сложно", "долго", "стресс", "срочно", "конфликт", "инцидент"];
  const proKeywords = ["документ", "план", "трениров", "ошиб", "формулиров", "подготов"];

  if (intenseKeywords.some((k) => text.includes(k))) return "intensive";
  if (proKeywords.some((k) => text.includes(k))) return "pro";
  return "start";
}

export default function DiagnosticPage() {
  const [step, setStep] = useState(0);
  const [helpIdx, setHelpIdx] = useState(0);
  const [reasons, setReasons] = useState<string[]>([]);
  const [otherReason, setOtherReason] = useState("");
  const [situation, setSituation] = useState("");
  const [history, setHistory] = useState("");
  const [goal, setGoal] = useState("");
  const [done, setDone] = useState(false);
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [resultPlan, setResultPlan] = useState<PlanKey | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = localStorage.getItem("diagnostic_draft_v2");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as {
        step?: number;
        reasons?: string[];
        otherReason?: string;
        situation?: string;
        history?: string;
        goal?: string;
      };
      setStep(Math.min(Math.max(parsed.step ?? 0, 0), 3));
      setReasons(parsed.reasons ?? []);
      setOtherReason(parsed.otherReason ?? "");
      setSituation(parsed.situation ?? "");
      setHistory(parsed.history ?? "");
      setGoal(parsed.goal ?? "");
    } catch {
      // ignore broken draft
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem(
      "diagnostic_draft_v2",
      JSON.stringify({ step, reasons, otherReason, situation, history, goal }),
    );
  }, [step, reasons, otherReason, situation, history, goal]);

  useEffect(() => {
    setHelpIdx(step);
  }, [step]);

  const progress = useMemo(() => Math.round((step / (STEP_TITLES.length - 1)) * 100), [step]);
  const minutesLeft = useMemo(() => Math.max(1, 4 - step), [step]);

  const recommended = useMemo(
    () => detectPlan({ reasons, situation, history, goal, other: otherReason }),
    [reasons, situation, history, goal, otherReason],
  );

  const canNext = useMemo(() => {
    if (step === 0) {
      if (reasons.length === 0) return false;
      if (reasons.includes("Другое") && otherReason.trim().length < 2) return false;
      return true;
    }
    if (step === 1) return situation.trim().length >= 12;
    if (step === 2) return history.trim().length >= 12;
    return goal.trim().length >= 8;
  }, [step, reasons, otherReason, situation, history, goal]);

  const toggleReason = (reason: string) => {
    setReasons((prev) => {
      if (prev.includes(reason)) return prev.filter((x) => x !== reason);
      if (prev.length >= 2) return [reason];
      return [...prev, reason];
    });
  };

  const saveResult = async () => {
    if (typeof window === "undefined") return;
    setIsSaving(true);
    setSubmitError(null);

    const payload = {
      reasons,
      other_reason: otherReason || null,
      situation,
      history,
      goal,
    };

    try {
      const apiUrl = toPublicApiUrl("/api/public/diagnostic");
      const res = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `HTTP ${res.status}`);
      }

      const data = (await res.json()) as { id: string; recommended_plan: PlanKey };

      localStorage.setItem("diagnostic_answers", JSON.stringify({ reasons, otherReason, situation, history, goal }));
      localStorage.setItem("recommended_plan", data.recommended_plan ?? recommended);
      localStorage.setItem("diagnostic_submission_id", data.id);
      setSubmissionId(data.id);
      setResultPlan(data.recommended_plan ?? recommended);
      setDone(true);
    } catch {
      setSubmitError("Не удалось сохранить диагностику на сервере. Проверьте подключение и попробуйте снова.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="public-page-stack diagnostic-page">
      <section className="diagnostic-layout">
        <article className="card pad diagnostic-main">
          <div className="diagnostic-head">
            <h1 className="h2">Диагностика</h1>
            <p className="small">Осталось ~{minutesLeft} мин</p>
          </div>

          <div className="diagnostic-stepper mt-12">
            {STEP_TITLES.map((title, idx) => (
              <div key={title} className={`diag-step ${idx <= step ? "active" : ""}`}>
                <span className="diag-step-num">{idx + 1}</span>
                <span className="diag-step-label">{title}</span>
              </div>
            ))}
          </div>

          <div className="diag-progress mt-10" aria-hidden>
            <span style={{ width: `${progress}%` }} />
          </div>

          {step === 0 ? (
            <div className="mt-16 stack">
              <h2 className="h3">Какая основная причина MPU?</h2>
              <p className="small">Можно выбрать несколько, но не более двух вариантов.</p>
              <div className="diag-chip-grid">
                {REASONS.map((reason) => {
                  const active = reasons.includes(reason);
                  return (
                    <button
                      type="button"
                      key={reason}
                      className={`diag-chip ${active ? "active" : ""}`}
                      onClick={() => toggleReason(reason)}
                    >
                      {reason}
                    </button>
                  );
                })}
              </div>

              {reasons.includes("Другое") ? (
                <div className="field mt-8">
                  <label className="label" htmlFor="diag-other">
                    Уточните в 1–2 словах
                  </label>
                  <Input
                    id="diag-other"
                    className="diag-input"
                    value={otherReason}
                    onChange={(e) => setOtherReason(e.target.value)}
                  />
                </div>
              ) : null}
            </div>
          ) : null}

          {step === 1 ? (
            <div className="mt-16 stack">
              <h2 className="h3">Опишите текущую ситуацию</h2>
              <p className="small">Коротко (1–3 предложения). Без деталей, которые вы не хотите указывать.</p>
              <textarea className="input diag-textarea" value={situation} onChange={(e) => setSituation(e.target.value)} />
              <p className="help">Пример: «Сейчас собираю документы и хочу подготовиться к интервью без ошибок в формулировках».</p>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="mt-16 stack">
              <h2 className="h3">Что уже сделано по подготовке?</h2>
              <p className="small">Коротко (1–3 предложения). Без деталей, которые вы не хотите указывать.</p>
              <textarea className="input diag-textarea" value={history} onChange={(e) => setHistory(e.target.value)} />
              <p className="help">Пример: «Есть базовые документы, но нет уверенности в структуре ответов и порядке шагов».</p>
            </div>
          ) : null}

          {step === 3 ? (
            <div className="mt-16 stack">
              <h2 className="h3">Какая цель по срокам?</h2>
              <p className="small">Коротко (1–3 предложения). Без деталей, которые вы не хотите указывать.</p>
              <textarea className="input diag-textarea" value={goal} onChange={(e) => setGoal(e.target.value)} />
              <p className="help">Пример: «Хочу пройти полную подготовку в ближайшие 6–8 недель с финальной проверкой».</p>
            </div>
          ) : null}

          <div className="hero-actions mt-16">
            <Button variant="ghost" disabled={step === 0} onClick={() => setStep((v) => Math.max(0, v - 1))}>
              Назад
            </Button>
            {step < STEP_TITLES.length - 1 ? (
              <Button disabled={!canNext} onClick={() => setStep((v) => Math.min(STEP_TITLES.length - 1, v + 1))}>
                Далее
              </Button>
            ) : (
              <Button disabled={!canNext || isSaving} onClick={saveResult}>
                {isSaving ? "Сохраняем..." : "Показать результат"}
              </Button>
            )}
          </div>

          {submitError ? <p className="help mt-8">{submitError}</p> : null}
        </article>

        <aside className="card pad diagnostic-side">
          <h3 className="h3">Помощь</h3>
          <div className="diag-help-grid mt-12">
            {HELP_ITEMS.map((item, idx) => (
              <button
                key={item.title}
                type="button"
                className={`diag-help-item ${helpIdx === idx ? "active" : ""}`}
                onClick={() => setHelpIdx(idx)}
              >
                <span className="diag-help-dot" />
                <span>{item.title}</span>
              </button>
            ))}
          </div>
          <div className="diag-help-detail mt-12">
            <p className="p">{HELP_ITEMS[helpIdx].text}</p>
          </div>
        </aside>
      </section>

      {done ? (
        <section className="card pad soft">
          <h2 className="h3">Результат диагностики</h2>
          <p className="p mt-10">
            Рекомендуемый формат подготовки:{" "}
            <strong>
              {(resultPlan ?? recommended) === "start" ? "Start" : (resultPlan ?? recommended) === "pro" ? "Pro" : "Intensive"}
            </strong>
            . Вы можете перейти к оплате или выбрать другой вариант вручную.
          </p>
          {submissionId ? <p className="help mt-8">ID диагностики: {submissionId}</p> : null}
          <div className="hero-actions">
            <Link href={`/pricing?plan=${resultPlan ?? recommended}`}>
              <Button>Выбрать формат и оплатить</Button>
            </Link>
            <Link href="/pricing">
              <Button variant="secondary">Смотреть все тарифы</Button>
            </Link>
          </div>
        </section>
      ) : null}
    </div>
  );
}