"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

type PlanKey = "start" | "pro" | "intensive";
type Task = { id: string; text: string; done: boolean };
type DashboardView = "overview" | "route" | "exam" | "dossier" | "evidence";

type Artifact = { id: "case" | "risk" | "interview" | "evidence"; pct: number };
type SessionCard = {
  id: number;
  title: string;
  goal: string;
  result: string;
  status: "not_started" | "in_progress" | "done";
};

type DayRun = {
  day: number;
  checkin: { anxiety: number; tension: number; confidence: number; note: string; done: boolean };
  task: { text: string; done: boolean };
  exam: { done: boolean; answers: string[] };
};

type Dossier = {
  reason: string;
  responsibility: string;
  changes: string;
  shortStory: string;
  redZones: string;
};

type Evidence = {
  abstinence: "none" | "in_progress" | "ready";
  therapy: "none" | "in_progress" | "ready";
  doctor: "none" | "in_progress" | "ready";
  notes: string;
};

type PersistedProgress = {
  v: 1;
  focus: string;
  tasks: Task[];
  dayRuns: DayRun[];
  sessions: SessionCard[];
  examIndex: number;
  examHistory: { q: string; a: string; score: number; fix: string }[];
  dossier: Dossier;
  evidence: Evidence;
};

function makeDefaultProgress(): PersistedProgress {
  return {
    v: 1,
    focus: "алкоголь",
    tasks: [
      { id: "t1", text: "Check-in: состояние 1–10", done: false },
      { id: "t2", text: "Одна задача дня", done: false },
      { id: "t3", text: "Мини-экзамен (2–3 вопроса)", done: false },
    ],
    dayRuns: Array.from({ length: 30 }, (_, i) => ({
      day: i + 1,
      checkin: { anxiety: 5, tension: 5, confidence: 5, note: "", done: false },
      task: { text: "Коротко опишите, что делаете вместо старого паттерна.", done: false },
      exam: { done: false, answers: [] },
    })),
    sessions: [
      { id: 1, title: "Intake + таймлайн", goal: "Собрать факты и порядок событий", result: "Таймлайн v1", status: "not_started" },
      { id: 2, title: "Причина и ответственность", goal: "Убрать оправдания", result: "Четкая позиция", status: "not_started" },
      { id: 3, title: "Разбор эпизода №1", goal: "Найти триггеры и точку выбора", result: "Карта эпизода", status: "not_started" },
      { id: 4, title: "Разбор эпизода №2", goal: "Сравнить паттерны", result: "Список повторов", status: "not_started" },
      { id: 5, title: "Риск-профиль", goal: "Ранние признаки и сценарии", result: "Профиль риска", status: "not_started" },
      { id: 6, title: "План изменений", goal: "Режим, среда, контроль", result: "План действий", status: "not_started" },
      { id: 7, title: "План предотвращения", goal: "Закрыть риск высокого давления", result: "Готовый план", status: "not_started" },
      { id: 8, title: "Интервью: базовый прогон", goal: "Проверить ядро ответов", result: "База ответов", status: "not_started" },
      { id: 9, title: "Интервью: провокации", goal: "Закрыть слабые места", result: "Финальные правки", status: "not_started" },
      { id: 10, title: "Финальный прогон", goal: "Собрать папку готовности", result: "Версия v1", status: "not_started" },
    ],
    examIndex: 0,
    examHistory: [],
    dossier: { reason: "", responsibility: "", changes: "", shortStory: "", redZones: "" },
    evidence: { abstinence: "none", therapy: "none", doctor: "none", notes: "" },
  };
}

const STORAGE = {
  plan: "recommended_plan",
  session: "prep_session_v7",
  diagnostic: "diagnostic_answers",
};

const PLAN_LABEL: Record<PlanKey, string> = { start: "Start", pro: "Pro", intensive: "Intensive" };

const ARTIFACT_LABEL: Record<Artifact["id"], string> = {
  case: "Досье",
  risk: "План предотвращения",
  interview: "Пакет интервью",
  evidence: "Подтверждения",
};

const EXAM_QUESTIONS = [
  "Почему вас направили на MPU?",
  "Что именно вы изменили за последние месяцы?",
  "Как вы действуете при высоком риске срыва?",
  "Что вы скажете на провокацию: почему вам можно верить?",
  "Опишите ваш план предотвращения повтора по шагам.",
];

function Button({
  children,
  onClick,
  size,
}: {
  children: ReactNode;
  onClick?: () => void;
  size?: "sm" | "md";
}) {
  const isSmall = size === "sm";
  return (
    <button
      className="btn"
      onClick={onClick}
      style={{
        border: "1px solid rgba(0,0,0,.06)",
        borderRadius: 16,
        background: "linear-gradient(180deg, #2bc866 0%, #1fb557 100%)",
        color: "#fff",
        fontWeight: 800,
        letterSpacing: "0.01em",
        padding: isSmall ? "8px 14px" : "11px 18px",
        boxShadow: "0 10px 22px rgba(34,197,94,.22)",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function toView(v: string | null): DashboardView {
  if (v === "route" || v === "exam" || v === "dossier" || v === "evidence" || v === "overview") return v;
  return "overview";
}

function calcPct(values: string[]): number {
  const filled = values.filter((v) => v.trim().length >= 10).length;
  return Math.round((filled / values.length) * 100);
}

function rangeFillStyle(value: number) {
  const pct = Math.max(0, Math.min(100, ((value - 1) / 9) * 100));
  return { background: `linear-gradient(90deg, #4a9e71 ${pct}%, #e1e8e4 ${pct}%)` };
}

export default function DashboardPage() {
  const params = useSearchParams();
  const view = toView(params.get("view"));

  const [loading, setLoading] = useState(true);
  const [meId, setMeId] = useState<string | null>(null);
  const saveTimerRef = useMemo(() => ({ id: null as number | null }), []);
  const saveAbortRef = useMemo(() => ({ ctrl: null as AbortController | null }), []);
  const [plan, setPlan] = useState<PlanKey>("start");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [focus, setFocus] = useState("алкоголь");

  const [dayRuns, setDayRuns] = useState<DayRun[]>([]);
  const [sessions, setSessions] = useState<SessionCard[]>([]);
  const [examIndex, setExamIndex] = useState(0);
  const [examAnswer, setExamAnswer] = useState("");
  const [examHistory, setExamHistory] = useState<{ q: string; a: string; score: number; fix: string }[]>([]);
  const [dossier, setDossier] = useState<Dossier>({
    reason: "",
    responsibility: "",
    changes: "",
    shortStory: "",
    redZones: "",
  });
  const [evidence, setEvidence] = useState<Evidence>({
    abstinence: "none",
    therapy: "none",
    doctor: "none",
    notes: "",
  });

  useEffect(() => {
    (async () => {
      const meP = fetch("/api/client/me", { cache: "no-store" });
      const statusP = fetch("/api/client/payments/status", { cache: "no-store" }).catch(() => null);
      const progressP = fetch("/api/client/progress", { cache: "no-store" }).catch(() => null);

      const [meRes, statusRes, progressRes] = await Promise.all([meP, statusP, progressP]);

      const meJson = await meRes.json().catch(() => null);
      if (!meRes.ok || !meJson?.data?.id) {
        window.location.href = "/pricing";
        return;
      }
      setMeId(String(meJson.data.id));

      const statusJson = await statusRes?.json().catch(() => null);
      if (!statusRes?.ok || !statusJson?.data?.program_active) {
        window.location.href = "/pricing";
        return;
      }

      // План берём из backend status, не из localStorage
      const backendPlan = statusJson?.data?.plan;
      if (backendPlan === "start" || backendPlan === "pro" || backendPlan === "intensive") {
        setPlan(backendPlan);
      }

      // Прогресс из БД
      const progressJson = await progressRes?.json().catch(() => null);
      const saved = progressJson?.data?.state_json as PersistedProgress | undefined;

      const apply = (p: PersistedProgress) => {
        setFocus(p.focus || "алкоголь");
        setTasks(p.tasks || []);
        setDayRuns(p.dayRuns || []);
        setSessions(p.sessions || []);
        setExamIndex(typeof p.examIndex === "number" ? p.examIndex : 0);
        setExamHistory(p.examHistory || []);
        if (p.dossier) setDossier(p.dossier);
        if (p.evidence) setEvidence(p.evidence);
      };

      if (saved && saved.v === 1) {
        apply(saved);
        // старые ключи больше не нужны (чтобы не путало)
        try {
          localStorage.removeItem(STORAGE.session);
          localStorage.removeItem(STORAGE.plan);
          localStorage.removeItem(STORAGE.diagnostic);
        } catch {}
        setLoading(false);
        return;
      }

      // Нет записи в БД — инициализируем дефолт и сразу сохраняем
      const fresh = makeDefaultProgress();
      apply(fresh);

      await fetch("/api/client/progress", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state_json: fresh }),
        cache: "no-store",
      }).catch(() => null);

      setLoading(false);
    })();
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!meId) return;
    if (!dayRuns.length || !sessions.length) return;

    if (saveTimerRef.id) window.clearTimeout(saveTimerRef.id);

    saveTimerRef.id = window.setTimeout(async () => {
      saveAbortRef.ctrl?.abort();
      const ctrl = new AbortController();
      saveAbortRef.ctrl = ctrl;

      const payload: PersistedProgress = {
        v: 1,
        focus,
        tasks,
        dayRuns,
        sessions,
        examIndex,
        examHistory,
        dossier,
        evidence,
      };

      await fetch("/api/client/progress", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state_json: payload }),
        cache: "no-store",
        signal: ctrl.signal,
      }).catch(() => null);
    }, 800);

    return () => {
      if (saveTimerRef.id) window.clearTimeout(saveTimerRef.id);
    };
  }, [loading, meId, focus, tasks, dayRuns, sessions, examIndex, examHistory, dossier, evidence]);

  const completedTasks = useMemo(() => tasks.filter((t) => t.done).length, [tasks]);
  const completedDays = useMemo(() => dayRuns.filter((d) => d.checkin.done && d.task.done && d.exam.done).length, [dayRuns]);
  const completedSessions = useMemo(() => sessions.filter((s) => s.status === "done").length, [sessions]);

  const artifacts = useMemo<Artifact[]>(() => {
    const casePct = calcPct([dossier.reason, dossier.responsibility, dossier.changes, dossier.shortStory, dossier.redZones]);
    const riskPct = Math.round(
      (((evidence.abstinence !== "none" ? 1 : 0) + (evidence.therapy !== "none" ? 1 : 0) + (evidence.doctor !== "none" ? 1 : 0)) /
        3) *
        100,
    );
    const interviewPct = Math.min(100, Math.round((examHistory.length / 12) * 100));
    const evidencePct = Math.round(
      (((evidence.abstinence === "ready" ? 1 : 0) + (evidence.therapy === "ready" ? 1 : 0) + (evidence.doctor === "ready" ? 1 : 0)) /
        3) *
        100,
    );
    return [
      { id: "case", pct: casePct },
      { id: "risk", pct: riskPct },
      { id: "interview", pct: interviewPct },
      { id: "evidence", pct: evidencePct },
    ];
  }, [dossier, evidence, examHistory.length]);

  const overallProgress = useMemo(() => {
    const artifactsAvg = artifacts.reduce((acc, a) => acc + a.pct, 0) / artifacts.length;
    const examPart = Math.min(100, (examHistory.length / 15) * 100);
    const sessionsPart = (completedSessions / 10) * 100;
    const rhythmPart = Math.min(100, (completedDays / 7) * 100);
    return Math.round(artifactsAvg * 0.45 + examPart * 0.3 + sessionsPart * 0.15 + rhythmPart * 0.1);
  }, [artifacts, examHistory.length, completedSessions, completedDays]);

  const nextStepHref = useMemo(() => {
    const day = dayRuns.find((d) => !(d.checkin.done && d.task.done && d.exam.done));
    if (day) return "/dashboard?view=route";
    const s = sessions.find((x) => x.status !== "done");
    if (s) return "/dashboard?view=exam";
    return "/dashboard?view=exam";
  }, [dayRuns, sessions]);

  const activeDay = useMemo(() => {
    const firstIncomplete = dayRuns.find((d) => !(d.checkin.done && d.task.done && d.exam.done));
    return firstIncomplete?.day ?? 30;
  }, [dayRuns]);

  const activeDayRun = useMemo(() => dayRuns.find((d) => d.day === activeDay), [dayRuns, activeDay]);

  const activeDayStep = useMemo(() => {
    if (!activeDayRun) return 1;
    if (!activeDayRun.checkin.done) return 1;
    if (!activeDayRun.task.done) return 2;
    if (!activeDayRun.exam.done) return 3;
    return 3;
  }, [activeDayRun]);

  const submitExam = () => {
    const answer = examAnswer.trim();
    if (!answer) return;
    const score = Math.max(30, Math.min(96, 45 + Math.round(answer.length / 8)));
    const fix = score < 70 ? "Добавьте конкретику: дата, действие, вывод." : "Уточните 1 факт и сократите вводную часть.";
    setExamHistory((prev) => [
      ...prev,
      { q: EXAM_QUESTIONS[examIndex % EXAM_QUESTIONS.length], a: answer, score, fix },
    ]);
    setExamIndex((v) => v + 1);
    setExamAnswer("");
  };

  if (loading) {
    return (
      <main className="cabinet-v2-main">
        <section className="cabinet-v2-hero">
          <h1 className="cabinet-v2-title">Загрузка кабинета…</h1>
        </section>
      </main>
    );
  }

  return (
    <main className="cabinet-v2-main">
      <nav className="cabinet-v2-nav cabinet-v2-nav-top">
        <a className={`navlink ${view === "overview" ? "active" : ""}`} href="/dashboard?view=overview">Обзор</a>
        <a className={`navlink ${view === "route" ? "active" : ""}`} href="/dashboard?view=route">Маршрут</a>
        <a className={`navlink ${view === "exam" ? "active" : ""}`} href="/dashboard?view=exam">Экзамен</a>
        <a className={`navlink ${view === "dossier" ? "active" : ""}`} href="/dashboard?view=dossier">Досье</a>
        <a className={`navlink ${view === "evidence" ? "active" : ""}`} href="/dashboard?view=evidence">Доказательства</a>
      </nav>

      <section className="cabinet-v2-hero">
        <div>
          <h1 className="cabinet-v2-title">Рабочий кабинет подготовки к MPU</h1>
          <p className="cabinet-v2-subtitle">Пошаговая подготовка: маршрут, экзамен, досье и подтверждения.</p>
        </div>
        <div className="cabinet-v2-chips">
          <span className="chip">План: {PLAN_LABEL[plan]}</span>
          <span className="chip">День: {Math.max(1, completedDays + 1)}/30</span>
          <span className="chip">Фокус: {focus}</span>
          <span className="chip">Прогресс: {overallProgress}%</span>
        </div>
      </section>

      {view === "overview" ? (
        <>
          <section className="cabinet-v2-overview-grid">
            <div className="cabinet-v2-status">
              <div className="cabinet-v2-status-top">
                <h2 className="h3">Общий прогресс</h2>
                <span className="cabinet-v2-score">{overallProgress}/100</span>
              </div>
              <div className="cabinet-v2-progress">
                <div style={{ width: `${overallProgress}%` }} />
              </div>
              <p className="small">Оценка готовности обновляется по заполненным разделам, сессиям и экзамену.</p>
            </div>

            <div className="cabinet-v2-status">
              <h2 className="h3">Следующий шаг</h2>
              <p className="small">Один целевой шаг на сегодня: без перегруза.</p>
              <a href={nextStepHref} style={{ marginTop: 12, display: "inline-block" }}>
                <Button>Начать</Button>
              </a>
            </div>

            <div className="cabinet-v2-status cabinet-v2-status-wide">
              <h2 className="h3">Папка готовности</h2>
              <div className="cabinet-v2-circle-grid" style={{ marginTop: 8 }}>
                {artifacts.map((a) => (
                  <a
                    key={a.id}
                    href={`/dashboard?view=${a.id === "evidence" ? "evidence" : "dossier"}`}
                    className="cabinet-v2-circle-item"
                    aria-label={`${ARTIFACT_LABEL[a.id]} ${a.pct}%`}
                  >
                    <div className="cabinet-v2-circle" style={{ ["--pct" as string]: a.pct }}>
                      <strong>{a.pct}%</strong>
                    </div>
                    <span>{ARTIFACT_LABEL[a.id]}</span>
                  </a>
                ))}
              </div>
            </div>
          </section>
        </>
      ) : null}

      {view === "route" ? (
        <section className="cabinet-v2-block">
          <h2 className="h3">Маршрут 30 дней</h2>
          <p className="small">Дни идут последовательно: сначала завершается текущий день, затем открывается следующий.</p>

          <div className="cabinet-v2-route-top">
            <div>
              <p className="small">Активный день</p>
              <strong>День {activeDay}</strong>
              <p className="small">Этап: {activeDayStep}/3</p>
            </div>
            <div>
              <p className="small">Пройдено дней</p>
              <strong>{completedDays} из 30</strong>
              <div className="cabinet-v2-progress-track">
                <span style={{ width: `${Math.round((completedDays / 30) * 100)}%` }} />
              </div>
            </div>
          </div>

          <div className="cabinet-v2-stage-line" role="list" aria-label="Этапы дня">
            <div className={`cabinet-v2-stage-pill ${activeDayStep === 1 ? "active" : activeDayRun?.checkin.done ? "done" : ""}`}>
              1. Оценка состояния
            </div>
            <div className={`cabinet-v2-stage-pill ${activeDayStep === 2 ? "active" : activeDayRun?.task.done ? "done" : ""}`}>
              2. Задача дня
            </div>
            <div className={`cabinet-v2-stage-pill ${activeDayStep === 3 ? "active" : activeDayRun?.exam.done ? "done" : ""}`}>
              3. Мини-экзамен
            </div>
          </div>

          {activeDayRun ? (
            <div className="cabinet-v2-dayrun">
              <h3 className="h3">День {activeDayRun.day}</h3>
              <p className="small" style={{ marginTop: 2 }}>
                Шаг {activeDayStep}/3
              </p>

              <div className="cabinet-v2-task-list" style={{ marginTop: 10 }}>
                {activeDayStep === 1 ? (
                  <div className="cabinet-v2-task-item cabinet-v2-stage-panel">
                    <div style={{ width: "100%" }}>
                      <strong>Оценка состояния</strong>
                      <p className="small">Отметьте состояние по шкале и добавьте 1–2 предложения по самочувствию.</p>

                      <div className="cabinet-v2-inline-fields">
                        <label className="cabinet-v2-range-field">
                          <span>Тревога</span>
                          <input
                            type="range"
                            min={1}
                            max={10}
                            value={activeDayRun.checkin.anxiety}
                            style={rangeFillStyle(activeDayRun.checkin.anxiety)}
                            onChange={(e) =>
                              setDayRuns((prev) =>
                                prev.map((r) =>
                                  r.day === activeDay ? { ...r, checkin: { ...r.checkin, anxiety: Number(e.target.value) || 1 } } : r,
                                ),
                              )
                            }
                          />
                          <strong>{activeDayRun.checkin.anxiety}/10</strong>
                        </label>

                        <label className="cabinet-v2-range-field">
                          <span>Напряжение</span>
                          <input
                            type="range"
                            min={1}
                            max={10}
                            value={activeDayRun.checkin.tension}
                            style={rangeFillStyle(activeDayRun.checkin.tension)}
                            onChange={(e) =>
                              setDayRuns((prev) =>
                                prev.map((r) =>
                                  r.day === activeDay ? { ...r, checkin: { ...r.checkin, tension: Number(e.target.value) || 1 } } : r,
                                ),
                              )
                            }
                          />
                          <strong>{activeDayRun.checkin.tension}/10</strong>
                        </label>

                        <label className="cabinet-v2-range-field">
                          <span>Уверенность</span>
                          <input
                            type="range"
                            min={1}
                            max={10}
                            value={activeDayRun.checkin.confidence}
                            style={rangeFillStyle(activeDayRun.checkin.confidence)}
                            onChange={(e) =>
                              setDayRuns((prev) =>
                                prev.map((r) =>
                                  r.day === activeDay ? { ...r, checkin: { ...r.checkin, confidence: Number(e.target.value) || 1 } } : r,
                                ),
                              )
                            }
                          />
                          <strong>{activeDayRun.checkin.confidence}/10</strong>
                        </label>
                      </div>

                      <textarea
                        className="cabinet-v2-input"
                        value={activeDayRun.checkin.note}
                        onChange={(e) =>
                          setDayRuns((prev) =>
                            prev.map((r) => (r.day === activeDay ? { ...r, checkin: { ...r.checkin, note: e.target.value } } : r)),
                          )
                        }
                        placeholder="Коротко: что было сегодня самым сложным и как вы справились"
                      />

                      <Button
                        size="sm"
                        onClick={() => {
                          setDayRuns((prev) => prev.map((r) => (r.day === activeDay ? { ...r, checkin: { ...r.checkin, done: true } } : r)));
                          setTasks((prev) => prev.map((t) => (t.id === "t1" ? { ...t, done: true } : t)));
                        }}
                      >
                        Сохранить и дальше
                      </Button>
                    </div>
                  </div>
                ) : null}

                {activeDayStep === 2 ? (
                  <div className="cabinet-v2-task-item cabinet-v2-stage-panel">
                    <div style={{ width: "100%" }}>
                      <strong>Задача дня</strong>
                      <p className="small">Один короткий фокус на сегодня.</p>

                      <textarea
                        className="cabinet-v2-input"
                        value={activeDayRun.task.text}
                        onChange={(e) =>
                          setDayRuns((prev) =>
                            prev.map((r) => (r.day === activeDay ? { ...r, task: { ...r.task, text: e.target.value } } : r)),
                          )
                        }
                      />

                      <Button
                        size="sm"
                        onClick={() => {
                          setDayRuns((prev) => prev.map((r) => (r.day === activeDay ? { ...r, task: { ...r.task, done: true } } : r)));
                          setTasks((prev) => prev.map((t) => (t.id === "t2" ? { ...t, done: true } : t)));
                        }}
                      >
                        Сохранить и дальше
                      </Button>
                    </div>
                  </div>
                ) : null}

                {activeDayStep === 3 ? (
                  <div className="cabinet-v2-task-item cabinet-v2-stage-panel">
                    <div style={{ width: "100%" }}>
                      <strong>Мини-экзамен</strong>
                      <p className="small">Вопрос: {EXAM_QUESTIONS[(activeDay - 1) % EXAM_QUESTIONS.length]}</p>

                      <textarea
                        className="cabinet-v2-input"
                        value={activeDayRun.exam.answers[0] || ""}
                        onChange={(e) =>
                          setDayRuns((prev) =>
                            prev.map((r) => (r.day === activeDay ? { ...r, exam: { ...r.exam, answers: [e.target.value] } } : r)),
                          )
                        }
                      />

                      <Button
                        size="sm"
                        onClick={() => {
                          setDayRuns((prev) => prev.map((r) => (r.day === activeDay ? { ...r, exam: { ...r.exam, done: true } } : r)));
                          setTasks((prev) => prev.map((t) => (t.id === "t3" ? { ...t, done: true } : t)));
                        }}
                      >
                        Завершить Day Run
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {view === "exam" ? (
        <section className="cabinet-v2-block">
          <h2 className="h3">Экзамен</h2>
          <p className="small">
            Прогресс: {examHistory.length}/{EXAM_QUESTIONS.length * 3} · Тип: {examIndex % 4 === 0 ? "provocation" : "core"}
          </p>

          <div className="cabinet-v2-task-item" style={{ marginTop: 10 }}>
            <span>Вопрос: {EXAM_QUESTIONS[examIndex % EXAM_QUESTIONS.length]}</span>
          </div>

          <div className="cabinet-v2-input-wrap">
            <textarea
              className="cabinet-v2-input"
              value={examAnswer}
              onChange={(e) => setExamAnswer(e.target.value)}
              placeholder="Ваш ответ"
            />
            <Button onClick={submitExam}>Отправить</Button>
          </div>

          <div className="cabinet-v2-task-list" style={{ marginTop: 10 }}>
            {examHistory
              .slice(-5)
              .reverse()
              .map((r, idx) => (
                <div key={idx} className="cabinet-v2-task-item" style={{ display: "block" }}>
                  <p className="small">
                    <strong>Оценка:</strong> {r.score}/100
                  </p>
                  <p className="small">
                    <strong>Исправить:</strong> {r.fix}
                  </p>
                </div>
              ))}
          </div>
        </section>
      ) : null}

      {view === "dossier" ? (
        <section className="cabinet-v2-block">
          <h2 className="h3">Досье</h2>
          <div className="cabinet-v2-input-wrap">
            <textarea
              className="cabinet-v2-input"
              placeholder="Причина MPU (2–4 предложения)"
              value={dossier.reason}
              onChange={(e) => setDossier((d) => ({ ...d, reason: e.target.value }))}
            />
            <textarea
              className="cabinet-v2-input"
              placeholder="Ответственность без оправданий"
              value={dossier.responsibility}
              onChange={(e) => setDossier((d) => ({ ...d, responsibility: e.target.value }))}
            />
            <textarea
              className="cabinet-v2-input"
              placeholder="Что изменилось в действиях"
              value={dossier.changes}
              onChange={(e) => setDossier((d) => ({ ...d, changes: e.target.value }))}
            />
            <textarea
              className="cabinet-v2-input"
              placeholder="История 90 секунд"
              value={dossier.shortStory}
              onChange={(e) => setDossier((d) => ({ ...d, shortStory: e.target.value }))}
            />
            <textarea
              className="cabinet-v2-input"
              placeholder="Опасные зоны формулировок"
              value={dossier.redZones}
              onChange={(e) => setDossier((d) => ({ ...d, redZones: e.target.value }))}
            />
          </div>
        </section>
      ) : null}

      {view === "evidence" ? (
        <section className="cabinet-v2-block">
          <h2 className="h3">Доказательства</h2>
          <div className="cabinet-v2-task-list">
            <label className="cabinet-v2-task-item">
              Abstinenznachweis
              <select
                value={evidence.abstinence}
                onChange={(e) => setEvidence((v) => ({ ...v, abstinence: e.target.value as Evidence["abstinence"] }))}
              >
                <option value="none">нет</option>
                <option value="in_progress">в процессе</option>
                <option value="ready">готово</option>
              </select>
            </label>

            <label className="cabinet-v2-task-item">
              Therapienachweis
              <select
                value={evidence.therapy}
                onChange={(e) => setEvidence((v) => ({ ...v, therapy: e.target.value as Evidence["therapy"] }))}
              >
                <option value="none">нет</option>
                <option value="in_progress">в процессе</option>
                <option value="ready">готово</option>
              </select>
            </label>

            <label className="cabinet-v2-task-item">
              Arztbericht
              <select
                value={evidence.doctor}
                onChange={(e) => setEvidence((v) => ({ ...v, doctor: e.target.value as Evidence["doctor"] }))}
              >
                <option value="none">нет</option>
                <option value="in_progress">в процессе</option>
                <option value="ready">готово</option>
              </select>
            </label>

            <textarea
              className="cabinet-v2-input"
              placeholder="Комментарий по слабым местам"
              value={evidence.notes}
              onChange={(e) => setEvidence((v) => ({ ...v, notes: e.target.value }))}
            />
          </div>
        </section>
      ) : null}

      <section className="cabinet-v2-status">
        <h2 className="h3">Сегодня выполнено</h2>
        <div className="cabinet-v2-progress">
          <div style={{ width: `${Math.round((completedTasks / Math.max(tasks.length, 1)) * 100)}%` }} />
        </div>
        <p className="small">
          {completedTasks}/{tasks.length} шага дневного протокола.
        </p>
      </section>
    </main>
  );
}
