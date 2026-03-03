"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { flushSync } from "react-dom";

const LOADER_MIN_MS = 400;
const LOADER_FAILSAFE_MS = 15000;

function isInternalAnchor(a: HTMLAnchorElement): boolean {
  const href = a.getAttribute("href") || "";
  if (!href) return false;
  if (href.startsWith("#")) return false;
  if (a.target === "_blank") return false;
  if (a.hasAttribute("download")) return false;
  if (a.getAttribute("data-no-loader") === "1") return false;

  try {
    const url = new URL(a.href, window.location.href);
    if (url.origin !== window.location.origin) return false;

    const samePage = url.pathname === window.location.pathname && url.search === window.location.search;
    if (samePage) return false;

    return true;
  } catch {
    return false;
  }
}

type UnderlineController = {
  sync: () => void;
};

const underlineControllers = new WeakMap<HTMLElement, UnderlineController>();

function initUnderlineNav(navEl: HTMLElement): UnderlineController {
  navEl.dataset.underline = "1";

  let indicator = navEl.querySelector(":scope > .nav-underline-indicator") as HTMLElement | null;
  if (!indicator) {
    indicator = document.createElement("span");
    indicator.className = "nav-underline-indicator";
    indicator.setAttribute("aria-hidden", "true");
    navEl.appendChild(indicator);
  }

  const INNER_PAD = 10;
  const currentElRef: { el: HTMLElement | null } = { el: null };

  const clearJsActive = () => {
    const prev = Array.from(navEl.querySelectorAll('.navlink[data-js-active="1"]')) as HTMLElement[];
    for (const el of prev) {
      el.classList.remove("active");
      el.removeAttribute("data-js-active");
    }
  };

  const normalizePath = (p: string) => {
    const x = (p || "/").trim();
    if (!x || x === "/") return "/";
    return x.endsWith("/") ? x.slice(0, -1) : x;
  };

  const scoreAnchor = (a: HTMLAnchorElement): number => {
    const rawHref = a.getAttribute("href") || "";
    if (!rawHref || rawHref.startsWith("#")) return -1;

    try {
      const url = new URL(a.href, window.location.href);
      if (url.origin !== window.location.origin) return -1;

      const curPath = normalizePath(window.location.pathname);
      const linkPath = normalizePath(url.pathname);

      if (curPath === linkPath) return 10_000; // точное совпадение — приоритет
      if (linkPath !== "/" && curPath.startsWith(linkPath + "/")) return 1_000 + linkPath.length; // вложенные — по длине
      return -1;
    } catch {
      return -1;
    }
  };

  const resolveActive = (mutateIfMissing: boolean): HTMLElement | null => {
    // 1) если компонент уже сам поставил active — не трогаем
    const explicit = navEl.querySelector(".navlink.active") as HTMLElement | null;
    if (explicit) return explicit;

    // 2) поддержка aria-current
    const aria = navEl.querySelector('.navlink[aria-current="page"], .navlink[aria-current="true"]') as HTMLElement | null;
    if (aria) return aria;

    // 3) пытаемся определить по href (это нужно для public header)
    const anchors = Array.from(navEl.querySelectorAll("a.navlink")) as HTMLAnchorElement[];
    if (!anchors.length) return null;

    let best: HTMLAnchorElement | null = null;
    let bestScore = -1;

    for (const a of anchors) {
      const s = scoreAnchor(a);
      if (s > bestScore) {
        bestScore = s;
        best = a;
      }
    }

    if (!best || bestScore < 0) return null;
    if (!mutateIfMissing) return best;

    // ставим active только “от JS” и только в этом nav
    clearJsActive();
    best.classList.add("active");
    best.setAttribute("data-js-active", "1");
    return best;
  };

  const hide = () => {
    indicator!.style.opacity = "0";
    indicator!.style.width = "0px";
  };

  const moveTo = (el: HTMLElement | null, reveal: boolean) => {
    if (!el) {
      currentElRef.el = null;
      hide();
      return;
    }

    const navRect = navEl.getBoundingClientRect();
    const r = el.getBoundingClientRect();

    const x = Math.max(0, r.left - navRect.left + INNER_PAD);
    const w = Math.max(8, r.width - INNER_PAD * 2);
    const y = Math.max(0, r.bottom - navRect.top - 6);

    indicator!.style.transform = `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0)`;
    indicator!.style.width = `${w.toFixed(2)}px`;
    indicator!.style.opacity = reveal ? "1" : "0";
    currentElRef.el = el;
  };

  const sync = () => {
    const active = resolveActive(true);
    moveTo(active, Boolean(active));
  };

  const onPointerOver = (e: PointerEvent) => {
    const target = e.target as Element | null;
    const a = (target?.closest?.(".navlink") as HTMLElement | null) ?? null;
    if (!a) return;
    if (!navEl.contains(a)) return;
    moveTo(a, true);
  };

  const onPointerLeave = () => {
    const active = resolveActive(true);
    moveTo(active, Boolean(active));
  };

  const onFocusIn = (e: FocusEvent) => {
    const target = e.target as Element | null;
    const a = (target?.closest?.(".navlink") as HTMLElement | null) ?? null;
    if (!a) return;
    if (!navEl.contains(a)) return;
    moveTo(a, true);
  };

  const onFocusOut = () => {
    const active = resolveActive(true);
    moveTo(active, Boolean(active));
  };

  navEl.addEventListener("pointerover", onPointerOver);
  navEl.addEventListener("pointerleave", onPointerLeave);
  navEl.addEventListener("focusin", onFocusIn);
  navEl.addEventListener("focusout", onFocusOut);

  const ro = new ResizeObserver(() => {
    if (currentElRef.el && navEl.contains(currentElRef.el)) {
      moveTo(currentElRef.el, true);
      return;
    }
    sync();
  });
  ro.observe(navEl);

  requestAnimationFrame(() => sync());
  window.setTimeout(() => sync(), 60);

  return { sync };
}

export default function PublicMotion() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const [navigating, setNavigating] = useState(false);

  const armedRef = useRef(false);
  const startedAtRef = useRef(0);

  const hideTimerRef = useRef<number | null>(null);
  const failsafeTimerRef = useRef<number | null>(null);
  const router = useRouter();

  const showLoaderNow = () => {
    armedRef.current = true;
    startedAtRef.current = performance.now();

    if (hideTimerRef.current) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    if (failsafeTimerRef.current) {
      window.clearTimeout(failsafeTimerRef.current);
      failsafeTimerRef.current = null;
    }

    // ВАЖНО: чтобы лоадер появился ДО того, как Next успеет “моргнуть” новым роутом
    flushSync(() => setNavigating(true));

    // страховка, чтобы не зависнуть навсегда при сбое навигации
    failsafeTimerRef.current = window.setTimeout(() => {
      armedRef.current = false;
      setNavigating(false);
      failsafeTimerRef.current = null;
    }, LOADER_FAILSAFE_MS);
  };

  const hideLoaderWithMinDuration = () => {
    if (!armedRef.current) return;

    const elapsed = performance.now() - startedAtRef.current;
    const remaining = Math.max(0, LOADER_MIN_MS - elapsed);

    if (hideTimerRef.current) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }

    hideTimerRef.current = window.setTimeout(() => {
      armedRef.current = false;

      if (failsafeTimerRef.current) {
        window.clearTimeout(failsafeTimerRef.current);
        failsafeTimerRef.current = null;
      }

      setNavigating(false);
      hideTimerRef.current = null;
    }, remaining);
  };

  useEffect(() => {
    const selector = ".cabinet-v2-nav, .public-header .nav";
    const navs = Array.from(document.querySelectorAll(selector)) as HTMLElement[];

    for (const navEl of navs) {
      if (!underlineControllers.has(navEl)) {
        underlineControllers.set(navEl, initUnderlineNav(navEl));
      }
      underlineControllers.get(navEl)!.sync();
    }
  }, [pathname, searchKey]);

  // Page transition loader (3 green bars)
  useEffect(() => {
    const onClickCapture = (e: MouseEvent) => {
      if (e.defaultPrevented) return;
      if (e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

      const target = e.target as Element | null;
      const a = (target?.closest?.("a") as HTMLAnchorElement | null) ?? null;
      if (!a) return;
      if (!isInternalAnchor(a)) return;

      let nextHref = "";
      try {
        const url = new URL(a.href, window.location.href);
        nextHref = `${url.pathname}${url.search}${url.hash}`;
      } catch {
        return;
      }

      // 1) показываем лоадер сразу
      e.preventDefault();
      showLoaderNow();

      // 2) даём браузеру 1 кадр нарисовать оверлей, затем пушим роут
      requestAnimationFrame(() => {
        router.push(nextHref);
      });
    };

    const onPopState = () => {
      showLoaderNow();
    };

    document.addEventListener("click", onClickCapture, true);
    window.addEventListener("popstate", onPopState);

    return () => {
      document.removeEventListener("click", onClickCapture, true);
      window.removeEventListener("popstate", onPopState);
    };
  }, [router]);

  // Когда роут реально сменился — прячем, но не раньше 400ms от момента клика
  useEffect(() => {
    hideLoaderWithMinDuration();
  }, [pathname, searchKey]);

  // Cleanup timers
  useEffect(() => {
    return () => {
      if (hideTimerRef.current) window.clearTimeout(hideTimerRef.current);
      if (failsafeTimerRef.current) window.clearTimeout(failsafeTimerRef.current);
    };
  }, []);

  // Scroll reveal (one-time) — с защитой от reload/scroll restore
  useEffect(() => {
    const root = document.querySelector("main.public-design-refactor");
    if (!root) return;

    const selector = [
      "[data-reveal]",
      ".card",
      ".journey-card",
      ".faq-acc-item",
      ".faq-item",
      ".clean-plan",
      ".pricing-plan-card",
      ".kpi",
      ".reason",
      ".support-split > *",
      ".cards3 > *",
      ".grid2 > *",
      ".steps-grid > *",
      ".journey-grid > *",
    ].join(", ");

    const nodes = Array.from(root.querySelectorAll(selector)) as HTMLElement[];
    if (!nodes.length) return;

    let idx = 0;
    for (const el of nodes) {
      if (el.dataset.revealInit === "1") continue;
      el.dataset.revealInit = "1";
      el.classList.add("reveal");
      const delay = Math.min(0.28, idx * 0.035);
      el.style.setProperty("--reveal-delay", `${delay}s`);
      idx += 1;
    }

    const markVisible = (el: HTMLElement) => {
      if (el.dataset.revealSeen === "1") return;
      el.dataset.revealSeen = "1";
      el.classList.add("reveal-in");
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const el = entry.target as HTMLElement;
          markVisible(el);
          observer.unobserve(el);
        }
      },
      { root: null, rootMargin: "0px 0px 160px 0px", threshold: 0.01 }
    );

    for (const el of nodes) {
      if (el.dataset.revealSeen === "1") continue;
      observer.observe(el);
    }

    let raf = 0;
    const flushPassed = () => {
      raf = 0;
      const limit = window.innerHeight + 160;

      for (const el of nodes) {
        if (el.dataset.revealSeen === "1") continue;
        const r = el.getBoundingClientRect();

        if (r.bottom < 0 || r.top <= limit) {
          markVisible(el);
          observer.unobserve(el);
        }
      }
    };

    const scheduleFlush = () => {
      if (raf) return;
      raf = window.requestAnimationFrame(flushPassed);
    };

    scheduleFlush();
    const t1 = window.setTimeout(scheduleFlush, 60);
    const t2 = window.setTimeout(scheduleFlush, 220);
    const t3 = window.setTimeout(scheduleFlush, 600);
    const t4 = window.setTimeout(scheduleFlush, 900);

    const onPageShow = () => scheduleFlush();
    window.addEventListener("pageshow", onPageShow);

    window.addEventListener("scroll", scheduleFlush, { passive: true });
    window.addEventListener("resize", scheduleFlush);

    return () => {
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("scroll", scheduleFlush);
      window.removeEventListener("resize", scheduleFlush);
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      window.clearTimeout(t3);
      window.clearTimeout(t4);
      if (raf) window.cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, [pathname]);

  if (!navigating) return null;

  return (
    <div className="route-loader" role="status" aria-label="Загрузка">
      <div className="route-loader-inner" aria-hidden="true">
        <span className="route-loader-bar" />
        <span className="route-loader-bar" />
        <span className="route-loader-bar" />
      </div>
    </div>
  );
}