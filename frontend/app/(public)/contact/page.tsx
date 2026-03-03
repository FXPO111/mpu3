"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function ContactPage() {
  const [ok, setOk] = useState(false);

  return (
    <div className="public-page-stack contact-page-xl">
      <section className="grid2 contact-grid">
        <article className="card pad">
          <div className="badge">Контакты</div>
          <h1 className="h2 mt-10">Поможем выбрать пакет и сценарий запуска</h1>
          <p className="p mt-12">
            Телефон: <a href="tel:+491752730963">+49 175 27 30 963</a><br />
            Email: <a href="mailto:info@mpu-praxis-dp.de">info@mpu-praxis-dp.de</a><br />
            Адрес: Viktoriastraße 32-36, 56068 Koblenz
          </p>

          <div className="hero-actions mt-16">
            <a href="tel:+491752730963"><Button variant="ghost">Позвонить сейчас</Button></a>
            <Link href="/pricing"><Button variant="secondary">Смотреть пакеты</Button></Link>
          </div>
        </article>

        <article className="card pad contact-form-card">
          <div className="badge">Заявка на консультацию</div>

          {ok ? (
            <div className="card pad soft mt-12">
              <div className="badge">Готово</div>
              <p className="p mt-8">Спасибо! Мы свяжемся с вами и предложим оптимальный формат запуска.</p>
            </div>
          ) : (
            <form
              className="contact-form"
              onSubmit={(e) => {
                e.preventDefault();
                setOk(true);
              }}
            >
              <Input placeholder="Имя и фамилия" />
              <Input placeholder="Email" type="email" />
              <Input placeholder="Телефон" />
              <Input placeholder="Ваш кейс / интересующий пакет" />
              <Button type="submit">Отправить заявку</Button>
            </form>
          )}
        </article>
      </section>

      <section className="card pad soft">
        <div className="badge">Перед оплатой важно уточнить</div>
        <div className="features mt-16 features-3">
          <article className="faq-item">
            <p className="faq-q">Срок, к которому нужен результат</p>
            <p className="faq-a">Это влияет на выбор пакета и интенсивность подготовки.</p>
          </article>
          <article className="faq-item">
            <p className="faq-q">Текущий статус документов</p>
            <p className="faq-a">Понимаем, что уже готово и что нужно собрать в первую очередь.</p>
          </article>
          <article className="faq-item">
            <p className="faq-q">Предыдущие попытки (если были)</p>
            <p className="faq-a">Это помогает сразу убрать старые ошибки в стратегии.</p>
          </article>
        </div>
      </section>
    </div>
  );
}