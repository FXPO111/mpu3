import type { ReactNode } from "react";
import AccountMenu from "@/app/_components/AccountMenu";

export default function CabinetLayout({ children }: { children: ReactNode }) {
  return (
    <div className="cabinet-v2-shell">
      <header className="cabinet-v2-header">
        <div className="container cabinet-v2-header-inner">
          <div className="cabinet-v2-brand">
            <span className="cabinet-v2-dot" />
            <span>MPU Praxis</span>
          </div>
          <AccountMenu compact />
        </div>
      </header>
      <div className="container page cabinet-v2-page">{children}</div>
    </div>
  );
}
