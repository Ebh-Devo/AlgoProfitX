interface FilterOption<T extends string> { value: T; label: string; count?: number }

interface FilterChipsProps<T extends string> {
  label: string;
  value: T;
  options: FilterOption<T>[];
  onChange: (value: T) => void;
}

/** Single-select filter rendered as a toggle-button group (aria-pressed), reachable with Tab. */
export function FilterChips<T extends string>({ label, value, options, onChange }: FilterChipsProps<T>) {
  return (
    <div className="filter-chips" role="group" aria-label={label}>
      {options.map(o => (
        <button
          key={o.value}
          type="button"
          className="filter-chip"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count !== undefined && <span className="filter-chip-count">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
