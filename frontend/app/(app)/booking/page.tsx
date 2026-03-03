import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";

export default function BookingPage() {
  return (
    <div className="grid2">
      <section className="card pad">
        <div className="badge">Booking</div>
        <h1 className="h2" style={{ marginTop: 10 }}>Создать обращение</h1>
        <p className="p">
          Заполни вводные. Это превращается в “кейс”, дальше AI задаёт уточняющие вопросы.
        </p>

        <div className="hr" />

        <div style={{ display: "grid", gap: 10 }}>
          <label style={{ display: "grid", gap: 6 }}>
            <span className="badge">Тема</span>
            <Input placeholder="Напр. алкоголь / ДТП / нарушение / суд…" />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            <span className="badge">Язык</span>
            <Input placeholder="DE или EN" />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            <span className="badge">Описание</span>
            <Textarea placeholder="Кто, когда, где, какие документы, сроки, что уже делал…" />
          </label>

          <Button>Создать кейс</Button>
        </div>
      </section>

      <section className="card pad">
        <h2 className="h2">Подсказка, что важно</h2>
        <ul style={{ margin: 0, paddingLeft: 18, color: "var(--muted)", lineHeight: 1.7 }}>
          <li>Хронология событий</li>
          <li>Причина нарушения/инцидента</li>
          <li>Что изменилось после (поведение/лечение/контроль)</li>
          <li>Документы: постановления, справки, курсы, терапия</li>
          <li>Почему риск устранён</li>
        </ul>
      </section>
    </div>
  );
}
