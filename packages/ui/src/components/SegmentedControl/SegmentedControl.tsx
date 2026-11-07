import type { ReactElement } from 'react';

import type { SegmentedOption } from '#ui/interfaces/segmented-option.interface';

import './SegmentedControl.css';

interface SegmentedControlProps<Value extends string> {
  /** Names the choice (the group's legend). */
  label: string;
  /** Show the legend only to assistive technology, when the context already says it. */
  isLabelHidden?: boolean;
  /** The radio group's name, unique on the page. */
  name: string;
  /** The chosen value. */
  value: Value;
  /** Two to five mutually exclusive choices. */
  options: SegmentedOption<Value>[];
  /** Show only the icons; the labels stay as accessible names. */
  isIconOnly?: boolean;
  /** Called with the newly chosen value. */
  onChange: (value: Value) => void;
}

/**
 * A row of mutually exclusive choices (Material 3 segmented button), built on native radio
 * buttons: Tab enters the group, the arrow keys move the choice.
 */
export const SegmentedControl = <Value extends string>({
  label,
  isLabelHidden = false,
  name,
  value,
  options,
  isIconOnly = false,
  onChange,
}: SegmentedControlProps<Value>): ReactElement => (
  <fieldset className="segmented-control">
    <legend
      className={isLabelHidden ? 'segmented-control__legend--hidden' : 'segmented-control__legend'}
    >
      {label}
    </legend>
    <div className="segmented-control__options">
      {options.map((option) => (
        <label
          key={option.value}
          className={`segmented-control__option${isIconOnly ? ' segmented-control__option--icon' : ''}`}
          title={isIconOnly ? option.label : undefined}
        >
          <input
            className="segmented-control__input"
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            disabled={option.isDisabled}
            onChange={() => onChange(option.value)}
          />
          {option.icon ? (
            <span className="segmented-control__icon" aria-hidden="true">
              {option.icon}
            </span>
          ) : null}
          <span className={isIconOnly ? 'segmented-control__text--hidden' : undefined}>
            {option.label}
          </span>
        </label>
      ))}
    </div>
  </fieldset>
);
