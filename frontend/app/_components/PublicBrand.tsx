"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function PublicBrand() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const tRef = useRef<number | null>(null);

  const close = () => {
    if (tRef.current) window.clearTimeout(tRef.current);
    tRef.current = null;
    setOpen(false);
    try { sessionStorage.setItem("mpu_hint_pricing_logo_v1", "1"); } catch {}
  };

  useEffect(() => {
    if (pathname !== "/pricing") return;

    try {
      if (sessionStorage.getItem("mpu_hint_pricing_logo_v1") === "1") return;
    } catch {}

    setOpen(true);
    tRef.current = window.setTimeout(close, 3000);

    return () => {
      if (tRef.current) window.clearTimeout(tRef.current);
      tRef.current = null;
    };
  }, [pathname]);

  return (
    <div className="brand-wrap">
      <Link href="/" className="brand" aria-label="MPU Praxis DP">
        <span className="brand-dot" />
        MPU Praxis DP
      </Link>

      {open ? (
        <div className="hint-bubble hint-bubble--brand" role="status" aria-live="polite">
          <div className="hint-bubble-text">Нажмите на логотип, чтобы вернуться на главную.</div>
          <button className="hint-bubble-close" type="button" onClick={close} aria-label="Закрыть">
            ✕
          </button>
        </div>
      ) : null}
    </div>
  );
}