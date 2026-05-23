import { RefObject, useEffect } from "react";

const FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(", ");

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => !element.hasAttribute("aria-hidden"),
  );
}

interface UseModalA11yOptions {
  containerRef: RefObject<HTMLElement | null>;
  enabled?: boolean;
  onEscape?: () => void;
  initialFocusRef?: RefObject<HTMLElement | null>;
}

export function useModalA11y({
  containerRef,
  enabled = true,
  onEscape,
  initialFocusRef,
}: UseModalA11yOptions): void {
  useEffect(() => {
    if (!enabled) return;
    const container = containerRef.current;
    if (!container) return;

    const previousFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusTarget =
      initialFocusRef?.current ?? focusableElements(container)[0] ?? container;
    focusTarget.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && onEscape) {
        event.preventDefault();
        onEscape();
        return;
      }

      if (event.key !== "Tab") return;
      const focusables = focusableElements(container);
      if (focusables.length === 0) {
        event.preventDefault();
        container.focus();
        return;
      }

      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    container.addEventListener("keydown", handleKeyDown);
    return () => {
      container.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, [containerRef, enabled, initialFocusRef, onEscape]);
}
