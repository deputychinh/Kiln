import { type KeyboardEvent, type ReactElement, useId, useRef, useState } from 'react';

import type { TabItem } from '#ui/interfaces/tab-item.interface';

import './Tabs.css';

interface TabsProps {
  /** Names the tab list, e.g. "Asset sections". */
  label: string;
  /** Two or more tabs; every panel stays mounted (hidden when not selected) so its state survives. */
  tabs: TabItem[];
  /** The open tab when uncontrolled (default: the first). */
  defaultSelectedId?: string;
  /** The open tab when controlled; pair with `onSelect`. */
  selectedId?: string;
  /** Called when a tab is chosen (click, or the arrow, Home and End keys). */
  onSelect?: (id: string) => void;
}

const NEXT_INDEX: Record<string, (index: number, count: number) => number> = {
  ArrowRight: (index, count) => (index + 1) % count,
  ArrowLeft: (index, count) => (index - 1 + count) % count,
  Home: () => 0,
  End: (_index, count) => count - 1,
};

/** WAI-ARIA tabs with automatic activation: one tab stop, arrow keys move between tabs. */
export const Tabs = ({
  label,
  tabs,
  defaultSelectedId,
  selectedId,
  onSelect,
}: TabsProps): ReactElement => {
  const baseId = useId();
  const [ownSelectedId, setOwnSelectedId] = useState(defaultSelectedId ?? tabs[0]?.id);
  const current = selectedId ?? ownSelectedId;
  const tabsRef = useRef<(HTMLButtonElement | null)[]>([]);

  const select = (id: string): void => {
    setOwnSelectedId(id);
    onSelect?.(id);
  };
  const onKeyDown = (event: KeyboardEvent, index: number): void => {
    const next = NEXT_INDEX[event.key]?.(index, tabs.length);
    const tab = next === undefined ? undefined : tabs[next];
    if (next === undefined || !tab) return;
    event.preventDefault();
    select(tab.id);
    tabsRef.current[next]?.focus();
  };

  return (
    <div className="tabs">
      <div className="tabs__list" role="tablist" aria-label={label}>
        {tabs.map((tab, index) => {
          const isSelected = tab.id === current;
          return (
            <button
              key={tab.id}
              ref={(element) => {
                tabsRef.current[index] = element;
              }}
              id={`${baseId}-tab-${tab.id}`}
              className="tabs__tab"
              type="button"
              role="tab"
              aria-selected={isSelected}
              aria-controls={`${baseId}-panel-${tab.id}`}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => select(tab.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
            >
              {tab.label}
              {/* The space keeps the count a separate word in the tab's name ("Versions 3"). */}
              {tab.badge === undefined ? null : (
                <>
                  {' '}
                  <span className="tabs__badge">{tab.badge}</span>
                </>
              )}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          id={`${baseId}-panel-${tab.id}`}
          className="tabs__panel"
          role="tabpanel"
          aria-labelledby={`${baseId}-tab-${tab.id}`}
          hidden={tab.id !== current}
        >
          {tab.panel}
        </div>
      ))}
    </div>
  );
};
