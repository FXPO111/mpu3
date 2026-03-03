import Link from "next/link";
import { Button } from "@/components/ui/Button";

const modules = [
  ["Диагностика", "Анализ исходной ситуации, документов и сроков."],
  ["Маршрут", "Пошаговый план подготовки с понятными задачами."],
  ["Практика", "Тренировки интервью и корректировка формулировок."],
  ["Контроль", "Проверка готовности и закрытие оставшихся рисков."],
];

export default function ServicesPage() {
  return (
    <div className="public-page-stack">
      <section className="card pad pricing-clean-hero">
        <div className="badge">Программа</div>
        <h1 className="h2 mt-10">Структурная система подготовки без перегруза</h1>
        <p className="lead mt-12">
          Программа собрана как рабочий цикл: каждый модуль имеет цель, результат и связь со следующим этапом.
        </p>
      </section>

      <section className="journey-grid journey-grid-4">
        {modules.map(([title, text], index) => (
          <article className="journey-card" key={title}>
            <div className="journey-top">
              <span className="journey-num">0{index + 1}</span>
              <p className="faq-q">{title}</p>
            </div>
            <p className="faq-a">{text}</p>
          </article>
        ))}
      </section>

      <section className="card pad soft">
        <div className="section-head">
          <div>
            <div className="badge">Запуск</div>
            <h2 className="h2 mt-10">Выберите пакет и переходите к подготовке</h2>
          </div>
          <Link href="/pricing"><Button>К тарифам</Button></Link>
        </div>
      </section>
    </div>
  );
}