"""Слоты публикации: генерация, занятость, подсказки свободного времени."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bots.ads import db
from bots.ads.config import config
from bots.ads.i18n import t, weekday

def tz() -> ZoneInfo:
    """Часовой пояс бота (меняется из панели без перезапуска)."""
    return ZoneInfo(config.timezone)


def tz_label(lang: str | None = "ru") -> str:
    return t(lang, "tz_msk") if config.timezone == "Europe/Moscow" else config.timezone


def now_ts() -> int:
    return db.now()


def slot_ts(day: date, hour: int) -> int:
    return int(datetime(day.year, day.month, day.day, hour, tzinfo=tz()).timestamp())


def ts_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz())


def fmt_day(day: date, lang: str | None = "ru") -> str:
    return f"{weekday(lang, day).capitalize()} {day:%d.%m}"


def fmt_ts(ts: int | None, lang: str | None = "ru") -> str:
    if not ts:
        return t(lang, "immediately")
    dt = ts_dt(ts)
    return t(lang, "ts", d=f"{dt:%d.%m}", wd=weekday(lang, dt), hm=f"{dt:%H:%M}", tz=tz_label(lang))


def day_code(day: date) -> int:
    return int(f"{day:%Y%m%d}")


def code_day(code: int) -> date:
    return datetime.strptime(str(code), "%Y%m%d").date()


def booking_days() -> list[date]:
    today = ts_dt(now_ts()).date()
    return [today + timedelta(days=i) for i in range(config.booking_days)]


def day_slots(day: date) -> list[int]:
    """Слоты дня, на которые ещё можно забронировать (с учётом минимального запаса времени)."""
    earliest = now_ts() + config.min_lead_minutes * 60
    return [ts for h in range(config.work_start, config.work_end + 1)
            if (ts := slot_ts(day, h)) >= earliest]


def all_slots() -> list[int]:
    return [ts for d in booking_days() for ts in day_slots(d)]


def is_bookable(ts: int) -> bool:
    return ts in set(all_slots())


async def load_busy(is_test: bool, exclude_order: int | None = None) -> dict[int, set[int]]:
    days = booking_days()
    start = slot_ts(days[0], 0)
    end = slot_ts(days[-1], 23)
    return await db.busy_map(start, end, is_test, exclude_order)


def busy_in(busy: dict[int, set[int]], ts: int, channel_ids: list[int]) -> set[int]:
    return busy.get(ts, set()) & set(channel_ids)


def free_slots(busy: dict[int, set[int]], channel_ids: list[int], after: int = 0, limit: int = 4) -> list[int]:
    """Ближайшие слоты, где свободны ВСЕ выбранные каналы."""
    result = []
    for ts in all_slots():
        if ts > after and not busy_in(busy, ts, channel_ids):
            result.append(ts)
            if len(result) >= limit:
                break
    return result


async def nearest_free(channel_ids: list[int], is_test: bool) -> int | None:
    busy = await load_busy(is_test)
    found = free_slots(busy, channel_ids, limit=1)
    return found[0] if found else None


def slot_ok(order) -> bool:
    """Время заказа ещё не прошло (или публикация «сразу»)."""
    return not order["publish_at"] or order["publish_at"] > now_ts()
