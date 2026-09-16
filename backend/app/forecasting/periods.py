"""Calendar-safe period operations shared by validation and forecasting."""

import calendar
from datetime import date, timedelta

from app.forecasting.models import ForecastFrequency


def next_period(period: date, frequency: ForecastFrequency) -> date:
    """Advance one exact calendar period without fixed-length month assumptions."""

    if frequency is ForecastFrequency.DAY:
        return period + timedelta(days=1)
    if frequency is ForecastFrequency.WEEK:
        return period + timedelta(days=7)
    year = period.year + (1 if period.month == 12 else 0)
    month = 1 if period.month == 12 else period.month + 1
    current_month_end = calendar.monthrange(period.year, period.month)[1]
    next_month_end = calendar.monthrange(year, month)[1]
    day = next_month_end if period.day == current_month_end else min(period.day, next_month_end)
    return date(year, month, day)
