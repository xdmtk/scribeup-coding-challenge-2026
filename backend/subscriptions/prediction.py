import re
from calendar import monthrange
from datetime import date, timedelta


CALENDAR_CYCLES = {"monthly": 1, "bimonthly": 2, "quarterly": 3,
                   "semiannual": 6, "yearly": 12}
FIXED_DAYS = {"weekly": 7, "biweekly": 14, "every four weeks": 28}


def _add_months(value: date, months: int, preserve_eom: bool) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    last_day = monthrange(year, month)[1]
    day = last_day if preserve_eom else min(value.day, last_day)
    return date(year, month, day)


def predict_next_charge(latest_charge: date, cadence: str, reference_date: date) -> date | None:
    """Return the first cadence occurrence strictly after the reference date."""
    # Calendar cadences advance month boundaries and preserve end-of-month intent;
    # fixed-day cadences advance an exact number of elapsed days instead.
    if cadence in CALENDAR_CYCLES:
        months = CALENDAR_CYCLES[cadence]
        preserve_eom = latest_charge.day == monthrange(latest_charge.year, latest_charge.month)[1]
        result = _add_months(latest_charge, months, preserve_eom)

        while result <= reference_date:
            result = _add_months(result, months, preserve_eom)

        return result

    # Named fixed cadences and detected custom cadences share exact-day arithmetic.
    days = FIXED_DAYS.get(cadence)
    match = re.fullmatch(r"every_(\d+)_days", cadence or "")
    if match:
        days = int(match.group(1))

    if not days:
        return None

    cycles = max(1, (reference_date - latest_charge).days // days + 1)
    return latest_charge + timedelta(days=cycles * days)
