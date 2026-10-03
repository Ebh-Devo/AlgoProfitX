import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem { id: string; label: string; content: ReactNode }

/** Accessible tabs: roving tabindex, Left/Right/Home/End navigation. */
export function Tabs({ items, label, initial }: { items: TabItem[]; label: string; initial?: string }) {
  const [active, setActive] = useState(initial ?? items[0]?.id);
  const base = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const move = (e: KeyboardEvent, index: number) => {
    const last = items.length - 1;
    const next = e.key === "ArrowRight" ? (index + 1) % items.length
      : e.key === "ArrowLeft" ? (index - 1 + items.length) % items.length
      : e.key === "Home" ? 0 : e.key === "End" ? last : -1;
    if (next < 0) return;
    e.preventDefault();
    setActive(items[next].id);
    refs.current[items[next].id]?.focus();
  };

  return (
    <div>
      <div className="tabs" role="tablist" aria-label={label}>
        {items.map((t, i) => (
          <button
            key={t.id}
            ref={el => { refs.current[t.id] = el; }}
            type="button"
            role="tab"
            id={`${base}-tab-${t.id}`}
            aria-selected={active === t.id}
            aria-controls={`${base}-panel-${t.id}`}
            tabIndex={active === t.id ? 0 : -1}
            className="tab"
            onClick={() => setActive(t.id)}
            onKeyDown={e => move(e, i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {items.map(t => (
        <div
          key={t.id}
          role="tabpanel"
          id={`${base}-panel-${t.id}`}
          aria-labelledby={`${base}-tab-${t.id}`}
          hidden={active !== t.id}
          className="tab-panel"
        >
          {active === t.id && t.content}
        </div>
      ))}
    </div>
  );
}
