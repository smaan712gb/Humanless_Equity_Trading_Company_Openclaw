"""Market calendar — holidays, sessions, and trading hour awareness."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum


class Session(str, Enum):
    CLOSED = "CLOSED"
    ETH_PRE_MARKET = "ETH_PRE_MARKET"
    RTH = "RTH"
    ETH_AFTER_HOURS = "ETH_AFTER_HOURS"
    OVERNIGHT = "OVERNIGHT"


# US Market Holidays 2026 (NYSE/NASDAQ Closed)
HOLIDAYS_2026 = {
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents' Day
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence Day observed
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
}

# Early close days (market closes at 13:00 ET)
EARLY_CLOSE_2026 = {
    date(2026, 11, 27),  # Day after Thanksgiving
    date(2026, 12, 24),  # Christmas Eve
}


def is_market_holiday(d: date | None = None) -> bool:
    """Check if the given date is a US market holiday."""
    d = d or date.today()
    if d.weekday() >= 5:  # Saturday/Sunday
        return True
    return d in HOLIDAYS_2026


def is_early_close(d: date | None = None) -> bool:
    """Check if the given date is an early close day."""
    d = d or date.today()
    return d in EARLY_CLOSE_2026


def get_close_time(d: date | None = None) -> time:
    """Get the RTH close time for the given date."""
    d = d or date.today()
    if is_early_close(d):
        return time(13, 0)
    return time(16, 0)


def get_flatten_time(d: date | None = None) -> time:
    """Get the time by which all intraday positions should be flattened."""
    d = d or date.today()
    if is_early_close(d):
        return time(12, 45)
    return time(19, 30)  # before ETH close, unless holding overnight


def get_current_session(now: datetime | None = None) -> Session:
    """Determine the current trading session."""
    now = now or datetime.now()
    d = now.date()
    t = now.time()

    if is_market_holiday(d):
        return Session.CLOSED

    if time(4, 0) <= t < time(9, 30):
        return Session.ETH_PRE_MARKET
    elif time(9, 30) <= t < get_close_time(d):
        return Session.RTH
    elif get_close_time(d) <= t < time(20, 0):
        return Session.ETH_AFTER_HOURS
    else:
        return Session.OVERNIGHT


def is_any_session_active(now: datetime | None = None) -> bool:
    """Check if any trading session (ETH or RTH) is currently active."""
    session = get_current_session(now)
    return session in (Session.ETH_PRE_MARKET, Session.RTH, Session.ETH_AFTER_HOURS)


def requires_outside_rth(now: datetime | None = None) -> bool:
    """Check if orders need outsideRth=True."""
    session = get_current_session(now)
    return session in (Session.ETH_PRE_MARKET, Session.ETH_AFTER_HOURS)


def get_position_size_multiplier(now: datetime | None = None) -> float:
    """Get the position size multiplier for the current session."""
    session = get_current_session(now)
    if session == Session.RTH:
        return 1.0
    elif session in (Session.ETH_PRE_MARKET, Session.ETH_AFTER_HOURS):
        return 0.5
    return 0.0  # CLOSED / OVERNIGHT — no new positions


def can_use_market_orders(now: datetime | None = None) -> bool:
    """Check if MARKET orders are allowed in the current session."""
    session = get_current_session(now)
    return session == Session.RTH


def next_trading_day(d: date | None = None) -> date:
    """Get the next date the market is open."""
    from datetime import timedelta
    d = d or date.today()
    d += timedelta(days=1)
    while is_market_holiday(d):
        d += timedelta(days=1)
    return d


def get_session_info() -> dict:
    """Get a complete snapshot of current market session state."""
    now = datetime.now()
    session = get_current_session(now)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S ET"),
        "session": session.value,
        "is_holiday": is_market_holiday(now.date()),
        "is_early_close": is_early_close(now.date()),
        "close_time": get_close_time(now.date()).strftime("%H:%M"),
        "can_trade": is_any_session_active(now),
        "outside_rth": requires_outside_rth(now),
        "size_multiplier": get_position_size_multiplier(now),
        "market_orders_ok": can_use_market_orders(now),
        "next_trading_day": next_trading_day(now.date()).strftime("%Y-%m-%d"),
    }
