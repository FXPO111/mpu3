import { Button } from "@/components/ui/Button";
import Link from "next/link";

export default function ExpertPage() {
  return (
    <div className="grid2">
      <section className="card pad">
        <div className="badge">Эксперт</div>
        <h1 className="h1" style={{ marginTop: 14 }}>Certified MPU specialist</h1>
        <p className="p">
          Языки: DE / EN. Работа: разбор кейса, подготовка структуры ответа,
          тренировка под типовые вопросы комиссии.
        </p>

        <div className="hr" />

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Link href="/login"><Button>Начать</Button></Link>
          <Link href="/pricing"><Button variant="secondary">Тарифы</Button></Link>
        </div>
      </section>

      <section className="card pad">
        <h2 className="h2">Что ты получишь</h2>
        <ul style={{ margin: 0, paddingLeft: 18, color: "var(--muted)", lineHeight: 1.7 }}>
          <li>Чёткую структуру истории (что/почему/как исправил)</li>
          <li>Список вопросов “как на интервью”</li>
          <li>Тренировку ответов с фиксацией слабых мест</li>
          <li>Историю кейса в кабинете</li>
        </ul>
      </section>
    </div>
  );
}
