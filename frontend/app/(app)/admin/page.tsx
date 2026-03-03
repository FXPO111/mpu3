import { Button } from "@/components/ui/Button";

export default function AdminPage() {
  const users = [
    { email: "a@mpu", plan: "Pro", balance: "€12", status: "active" },
    { email: "b@mpu", plan: "Start", balance: "€0", status: "trial" },
    { email: "c@mpu", plan: "Team", balance: "€41", status: "active" },
  ];

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="card pad">
        <div className="badge">Admin</div>
        <h1 className="h2" style={{ marginTop: 10 }}>Панель управления</h1>
        <p className="p">Пользователи, баланс, статусы, платежи — всё сюда.</p>
      </div>

      <div className="card pad">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <h2 className="h2" style={{ margin: 0 }}>Users</h2>
          <Button variant="secondary" size="sm">Экспорт</Button>
        </div>

        <div className="hr" />

        <div style={{ display: "grid", gap: 10 }}>
          {users.map((u) => (
            <div key={u.email} className="card pad" style={{ boxShadow: "none" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontWeight: 800 }}>{u.email}</div>
                  <div className="p">{u.plan}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="badge">{u.status}</div>
                  <div className="p" style={{ marginTop: 6 }}>{u.balance}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
