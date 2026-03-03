const principles = [
  ["Процесс важнее обещаний", "Каждый блок в продукте связан с конкретным этапом подготовки и измеримым результатом."],
  ["Прозрачность для клиента", "Стоимость, наполнение и срок сопровождения понятны до оплаты."],
  ["Фокус на применимости", "Система готовит к реальному интервью MPU, а не к абстрактной теории."],
];

export default function AboutPage() {
  return (
    <div className="public-page-stack about-page-xl">
      <section className="card pad about-page">
        <div className="badge">О проекте</div>
        <h1 className="h2 mt-10">MPU Praxis DP: переход от «сайта услуг» к полноценному digital-продукту</h1>
        <p className="lead mt-12">
          Наша задача — сделать подготовку масштабируемой и управляемой. Клиент должен видеть понятный маршрут,
          стоимость, результат каждого этапа и реальный прогресс до финальной проверки.
        </p>
      </section>

      <section className="features features-3">
        {principles.map(([title, text]) => (
          <article className="card pad soft" key={title}>
            <div className="badge">{title}</div>
            <p className="p mt-10">{text}</p>
          </article>
        ))}
      </section>
    </div>
  );
}