import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="container" style={{ padding: "60px 0" }}>
      <div className="card pad" style={{ width: "min(520px, 100%)", margin: "0 auto" }}>
        {children}
      </div>
    </main>
  );
}
