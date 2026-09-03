import { CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { businessDate } from "../lib/format";
import {
  formatJalaliNumeric,
  gregorianToJalali,
  JALALI_MONTHS,
  JALALI_WEEKDAYS,
  jalaliFirstWeekday,
  jalaliMonthLength,
  jalaliToGregorian,
  persianNumber,
  type JalaliDateParts,
} from "../lib/jalali";

interface JalaliDatePickerProps {
  name?: string;
  value?: string;
  defaultValue?: string;
  min?: string;
  max?: string;
  onChange?: (value: string) => void;
  required?: boolean;
  allowClear?: boolean;
  ariaLabel?: string;
  className?: string;
}

const moveMonth = (value: JalaliDateParts, amount: number): JalaliDateParts => {
  const index = value.year * 12 + value.month - 1 + amount;
  return { year: Math.floor(index / 12), month: (index % 12) + 1, day: 1 };
};

export function JalaliDatePicker({
  name,
  value,
  defaultValue,
  min,
  max,
  onChange,
  required = false,
  allowClear = false,
  ariaLabel = "انتخاب تاریخ شمسی",
  className = "",
}: JalaliDatePickerProps) {
  const controlled = value !== undefined;
  const [internalValue, setInternalValue] = useState(defaultValue || "");
  const selectedValue = controlled ? value || "" : internalValue;
  const selectedParts = gregorianToJalali(selectedValue);
  const today = businessDate();
  const todayParts = gregorianToJalali(today)!;
  const [visibleMonth, setVisibleMonth] = useState<JalaliDateParts>(selectedParts || todayParts);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const minParts = min ? gregorianToJalali(min) : null;
  const maxParts = max ? gregorianToJalali(max) : null;
  const firstYear = minParts?.year ?? todayParts.year - 50;
  const lastYear = maxParts?.year ?? todayParts.year + 10;
  const years = useMemo(
    () => Array.from({ length: Math.max(1, lastYear - firstYear + 1) }, (_, index) => firstYear + index),
    [firstYear, lastYear],
  );

  useEffect(() => {
    const nextSelected = gregorianToJalali(selectedValue);
    if (nextSelected) setVisibleMonth(nextSelected);
  }, [selectedValue]);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const commit = (nextValue: string) => {
    if (!controlled) setInternalValue(nextValue);
    onChange?.(nextValue);
  };
  const selectDay = (day: number) => {
    const iso = jalaliToGregorian(visibleMonth.year, visibleMonth.month, day);
    if (!iso || (min && iso < min) || (max && iso > max)) return;
    commit(iso);
    setOpen(false);
  };
  const changeMonth = (amount: number) => {
    const next = moveMonth(visibleMonth, amount);
    if (next.year < firstYear || next.year > lastYear) return;
    setVisibleMonth(next);
  };
  const selectToday = () => {
    setVisibleMonth(todayParts);
    if ((min && today < min) || (max && today > max)) return;
    commit(today);
    setOpen(false);
  };
  const monthLength = jalaliMonthLength(visibleMonth.year, visibleMonth.month);
  const leadingDays = jalaliFirstWeekday(visibleMonth.year, visibleMonth.month);
  const cells = Array.from({ length: leadingDays + monthLength }, (_, index) =>
    index < leadingDays ? null : index - leadingDays + 1,
  );

  return (
    <div ref={root} className={`jalali-date-picker ${open ? "is-open" : ""} ${className}`.trim()}>
      <input type="hidden" name={name} value={selectedValue} />
      <button
        type="button"
        className="jalali-date-trigger"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={ariaLabel}
        aria-required={required}
      >
        <CalendarDays />
        <span className={selectedParts ? "" : "placeholder"}>
          {selectedParts ? formatJalaliNumeric(selectedParts) : "انتخاب تاریخ"}
        </span>
        <ChevronDown className="jalali-date-chevron" />
      </button>

      {open && (
        <div className="jalali-calendar" role="dialog" aria-label={ariaLabel}>
          <header>
            <button type="button" onClick={() => changeMonth(-1)} aria-label="ماه قبل"><ChevronRight /></button>
            <div>
              <strong>{JALALI_MONTHS[visibleMonth.month - 1]}</strong>
              <select
                value={visibleMonth.year}
                onChange={(event) => setVisibleMonth((current) => ({ ...current, year: Number(event.target.value) }))}
                aria-label="سال شمسی"
              >
                {years.map((year) => <option key={year} value={year}>{persianNumber(year)}</option>)}
              </select>
            </div>
            <button type="button" onClick={() => changeMonth(1)} aria-label="ماه بعد"><ChevronLeft /></button>
          </header>
          <div className="jalali-weekdays">
            {JALALI_WEEKDAYS.map((weekday) => <span key={weekday}>{weekday}</span>)}
          </div>
          <div className="jalali-days">
            {cells.map((day, index) => {
              if (day === null) return <i key={`empty-${index}`} />;
              const iso = jalaliToGregorian(visibleMonth.year, visibleMonth.month, day);
              const disabled = !iso || Boolean((min && iso < min) || (max && iso > max));
              const selected = Boolean(iso && iso === selectedValue);
              const isToday = Boolean(iso && iso === today);
              return (
                <button
                  type="button"
                  key={day}
                  disabled={disabled}
                  className={`${selected ? "selected" : ""} ${isToday ? "today" : ""}`.trim()}
                  onClick={() => selectDay(day)}
                  aria-label={`${persianNumber(day)} ${JALALI_MONTHS[visibleMonth.month - 1]} ${persianNumber(visibleMonth.year)}`}
                >
                  {selected ? <Check /> : persianNumber(day)}
                </button>
              );
            })}
          </div>
          <footer>
            <button type="button" onClick={selectToday}><RotateCcw /> امروز</button>
            {allowClear && selectedValue && <button type="button" className="clear" onClick={() => { commit(""); setOpen(false); }}><X /> پاک کردن</button>}
          </footer>
        </div>
      )}
    </div>
  );
}
