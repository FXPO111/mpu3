"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

const STEPS = [
  { k: "reason", title: "Причина MPU", hint: "Алкоголь / вещества / баллы / агрессия / другое" },
  { k: "timeline", title: "Хронология", hint: "Когда произошло, какие решения уже были приняты" },
  { k: "changes", title: "Изменения", hint: "Какие действия уже сделаны: курсы, терапия, анализы, поведение" },
  { k: "docs", title: "Документы", hint: "Что готово сейчас и что необходимо собрать" },
  { k: "goal", title: "Цель по срокам", hint: "Когда планируете выход на финальный этап MPU" },
];

export default function StartPage() {
  const [i, setI] = useState(0);
  const [data, setData] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);

  const step = STEPS[i];
  const value = data[step.k] ?? "";
  const canNext = value.trim().length >= 8;
  const progress = useMemo(() => Math.round(((i + 1) / STEPS.length) * 100), [i]);

  return (
    <div className="public-page-stack start-page-xl">
      <section className="card pad">
        <div className="badge">Стартовая диагностика • шаг {i + 1}/{STEPS.length} • {progress}%</div>
        <h1 className="h2 mt-10">{step.title}</h1>
        <p className="p mt-8">{step.hint}</p>

        <div className="mt-12">
          <Input
            placeholder="Введите коротко и по существу"
            value={value}
            onChange={(e) => setData((p) => ({ ...p, [step.k]: e.target.value }))}
          />
        </div>

        <div className="hero-actions">
          <Button
            variant="ghost"
            disabled={i === 0}
            onClick={() => setI((v) => Math.max(0, v - 1))}
          >
            Назад
          </Button>

          {i < STEPS.length - 1 ? (
            <Button disabled={!canNext} onClick={() => setI((v) => Math.min(STEPS.length - 1, v + 1))}>
              Далее
            </Button>
          ) : (
            <Button
              disabled={!canNext}
              onClick={() => {
                localStorage.setItem("mpu_draft", JSON.stringify(data));
                setDone(true);
              }}
            >
              Сохранить диагностику
            </Button>
          )}
        </div>
      </section>

      {done && (
        <section className="card pad soft">
          <div className="badge">Диагностика сохранена</div>
          <p className="p mt-10">
            Следующий шаг — выбор пакета. На основе диагностики маршрут подготовки уже сформирован,
            после оплаты активируется полный доступ к программе.
          </p>
          <div className="hero-actions">
            <Link href="/pricing"><Button>Выбрать пакет</Button></Link>
            <Link href="/services"><Button variant="secondary">Посмотреть модули программы</Button></Link>
          </div>
        </section>
      )}

      <section className="card pad soft">
        <div className="badge">Что вы получите после старта</div>
        <div className="steps mt-16">
          <article className="faq-item">
            <p className="faq-q">Карту рисков по кейсу</p>
            <p className="faq-a">Понятно, какие зоны требуют проработки в первую очередь.</p>
          </article>
          <article className="faq-item">
            <p className="faq-q">Пошаговый маршрут</p>
            <p className="faq-a">Чёткий план с этапами и дедлайнами без лишнего шума.</p>
          </article>
          <article className="faq-item">
            <p className="faq-q">Подготовку к интервью</p>
            <p className="faq-a">Системные тренировки и контроль качества ответов.</p>
          </article>
        </div>
      </section>
    </div>
  );
}