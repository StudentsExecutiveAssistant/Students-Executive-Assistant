"""Розбір і форматування дат, періодів та часових проміжків українською мовою."""
from __future__ import annotations

import re
from datetime import date

MONTHS = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]
MONTHS_NOM = [
    "січень", "лютий", "березень", "квітень", "травень", "червень",
    "липень", "серпень", "вересень", "жовтень", "листопад", "грудень",
]
_MONTH_MAP = {m: i for i, m in enumerate(MONTHS, 1)} | {m: i for i, m in enumerate(MONTHS_NOM, 1)}

ScheduleItem = tuple[date, date, tuple[int, int | None] | None]

_YEAR_SUFFIX_RE = re.compile(r"(?:\s+року|(?:\s+|(?<=\d))р\.?)$", re.I)
_PART_SPLIT_RE = re.compile(r"[.\-/ ]+")
_DATE_TOKENS_RE = re.compile(r"[\n;,]+(?:\s*(?:та|і|й)\s+)?|\s+(?:та|і|й)\s+", re.I)
_SCHED_TOKENS_RE = re.compile(
    r"[\n;]+(?:\s*(?:та|і|й)\s+)?|,(?!\s*\d{1,2}(?::\d{2}|\.(?:00|1[3-9]|[2-5]\d)))(?:\s*(?:та|і|й)\s+)?|\s+(?:та|і|й)\s+",
    re.I,
)
_FROM_PREFIX_RE = re.compile(r"^(?:з|від)\s+", re.I)
_TO_INFIX_RE = re.compile(r"\s+(?:по|до)\s+", re.I)
_DASH_SPLIT_RE = re.compile(r"\s*[–—-]\s*")
_TIME_ONE_RE = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?")

_TIME_SUFFIX_RES = (
    re.compile(
        r"\s+(?:з|о|об)\s+(\d{1,2}(?:[:.]\d{2})?)"
        r"(?:\s*(?:год\.?\s*)?(?:[-–—]|до)\s*(\d{1,2}(?:[:.]\d{2})?))?(?:\s*год\.?)?$",
        re.I,
    ),
    re.compile(
        r"\s+(\d{1,2}(?::\d{2}|\.(?:00|1[3-9]|[2-5]\d))"
        r"(?:\s*[-–—]\s*\d{1,2}(?::\d{2}|\.(?:00|1[3-9]|[2-5]\d)))?)(?:\s*год\.?)?$",
        re.I,
    ),
    re.compile(r"\s+(\d{1,2}\s*[-–—]\s*\d{1,2})(?:\s*год\.?)?$", re.I),
)


def join_uk(parts: list[str]) -> str:
    """Об'єднує непорожні частини комами та сполучником «та» перед останнім елементом."""
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " та " + parts[-1]


def _parse_part(s: str, right: date | None, default_year: int) -> date:
    """Перетворює фрагмент дати ('16', '16.09', '26 листопада 2026') у date, запозичуючи місяць/рік справа."""
    cleaned = _YEAR_SUFFIX_RE.sub("", s.strip()).strip()
    bits = [b for b in _PART_SPLIT_RE.split(cleaned) if b]
    if not bits or len(bits) > 3 or not bits[0].isdigit():
        raise ValueError(f"Не можу розпізнати «{s}»")
    day = int(bits[0])
    if len(bits) > 1:
        m_raw = bits[1].lower()
        if m_raw.isdigit():
            month = int(m_raw)
        elif m_raw in _MONTH_MAP:
            month = _MONTH_MAP[m_raw]
        else:
            raise ValueError(f"Не можу розпізнати «{s}»")
    else:
        month = right.month if right else None
    if month is None:
        raise ValueError("Вкажіть місяць, наприклад 16.09 або 16.09.2026")
    if len(bits) > 2:
        if not bits[2].isdigit():
            raise ValueError(f"Не можу розпізнати «{s}»")
        year = int(bits[2])
        year += 2000 if year < 100 else 0
    else:
        year = right.year if right else default_year
    if not 1 <= month <= 12:
        raise ValueError(
            f"Місяць має бути від 1 до 12, а не {month} (у «{s}»). "
            "Пишіть дату у форматі ДД.ММ.РРРР, наприклад 15.11.2026"
        )
    if not 1 <= year <= 9999:
        raise ValueError(f"Некоректний рік «{year}» у «{s}»")
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError(
            f"Неіснуючий день {day} для {month:02d}.{year} (у «{s}»). "
            "Пишіть дату у форматі ДД.ММ.РРРР"
        ) from None


def _split_date_tokens(text: str) -> list[str]:
    return [t.strip() for t in _DATE_TOKENS_RE.split(text.strip()) if t.strip()]


def _parse_date_token(tok: str, right: date | None, default_year: int) -> tuple[date, date]:
    cleaned = _FROM_PREFIX_RE.sub("", tok.strip())
    cleaned = _TO_INFIX_RE.sub(" - ", cleaned)
    parts = [p for p in _DASH_SPLIT_RE.split(cleaned) if p]
    if not parts:
        raise ValueError(f"Не можу розпізнати «{tok}»")
    if len(parts) > 2:
        raise ValueError(f"Забагато «-» у «{tok}»")
    end = _parse_part(parts[-1], right, default_year)
    start = _parse_part(parts[0], end, default_year) if len(parts) == 2 else end
    if start > end:
        raise ValueError(f"Початок після кінця: «{tok}»")
    return start, end


def _resolve_date_tokens(date_tokens: list[str], default_year: int) -> list[tuple[date, date]]:
    items: list[tuple[date, date]] = []
    right: date | None = None
    for tok in reversed(date_tokens):
        start, end = _parse_date_token(tok, right, default_year)
        items.append((start, end))
        right = start
    items.reverse()
    return items


def parse_dates(text: str, default_year: int | None = None) -> list[tuple[date, date]]:
    default_year = default_year or date.today().year
    tokens = _split_date_tokens(text)
    if not tokens:
        raise ValueError("Порожня дата")
    return _resolve_date_tokens(tokens, default_year)


def _fmt(s: date, e: date, *, with_month: bool = True, with_year: bool = True) -> str:
    mo = f" {MONTHS[e.month - 1]}" if with_month else ""
    yr = f" {e.year} року" if with_year else ""
    if s == e:
        return f"{s.day}{mo}{yr}"
    if (s.month, s.year) == (e.month, e.year):
        return f"{s.day}-{e.day}{mo}{yr}"
    if s.year == e.year:
        return f"з {s.day} {MONTHS[s.month - 1]} до {e.day} {MONTHS[e.month - 1]}{yr}"
    return f"з {s.day} {MONTHS[s.month - 1]} {s.year} до {e.day} {MONTHS[e.month - 1]} {e.year} року"


def _format_date_items(items: list[tuple[date, date]], *, keep_month: bool = False) -> str:
    parts = []
    for i, (s, e) in enumerate(items):
        nxt = items[i + 1] if i + 1 < len(items) else None
        same_year = nxt is not None and e.year == nxt[1].year
        same_month = not keep_month and same_year and s.month == e.month == nxt[0].month == nxt[1].month
        parts.append(_fmt(s, e, with_month=not same_month, with_year=not same_year))
    return join_uk(parts)


def format_dates(text: str, default_year: int | None = None) -> str:
    """Форматує дати для тексту клопотання; префікс '!' залишає введений текст без змін."""
    text = text.strip()
    if text.startswith("!"):
        return text[1:].strip()
    return _format_date_items(parse_dates(text, default_year))


def parse_time(text: str) -> tuple[int, int | None]:
    """Перетворює '17:00-20:00' або '17:00' на хвилини від початку доби."""
    def one(x: str) -> int:
        m = _TIME_ONE_RE.fullmatch(x.strip())
        if not m:
            raise ValueError(f"Не можу розпізнати час «{x}»")
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h > 23 or mi > 59:
            raise ValueError(f"Некоректний час «{x}»")
        return h * 60 + mi

    parts = [p for p in _DASH_SPLIT_RE.split(text.strip()) if p]
    if len(parts) == 1:
        return one(parts[0]), None
    if len(parts) == 2:
        return one(parts[0]), one(parts[1])
    raise ValueError("Вкажіть час у форматі 17:00-20:00")


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d} год"


def _fmt_time(a: int, b: int | None) -> str:
    return f"о {_hhmm(a)}" if b is None else f"з {_hhmm(a)} до {_hhmm(b)}"


def format_time(text: str) -> str:
    text = text.strip()
    if text.startswith("!"):
        return text[1:].strip()
    return _fmt_time(*parse_time(text))


def _split_schedule_token(tok: str) -> tuple[str, tuple[int, int | None] | None]:
    for idx, rx in enumerate(_TIME_SUFFIX_RES):
        m = rx.search(tok)
        if not m:
            continue
        date_part = tok[:m.start()].strip().rstrip(",")
        if not date_part:
            continue
        if idx == 0:
            t1, t2 = m.group(1), m.group(2)
            tm = parse_time(f"{t1}-{t2}" if t2 else t1)
        else:
            tm = parse_time(m.group(1))
        return date_part, tm
    return tok, None


def parse_schedule(text: str, default_year: int | None = None, *, allow_time: bool = True) -> list[ScheduleItem]:
    default_year = default_year or date.today().year
    tokens = [t.strip() for t in _SCHED_TOKENS_RE.split(text.strip()) if t.strip()]
    if not tokens:
        raise ValueError("Порожня дата")
    split_tokens = [_split_schedule_token(tok) for tok in tokens]
    has_time = [tm is not None for _, tm in split_tokens]
    if not allow_time and any(has_time):
        raise ValueError("Для цього типу клопотання вкажіть лише дати без годин")
    if any(has_time) and not all(has_time):
        raise ValueError("Вкажіть час для кожної дати або для жодної (час запитаємо окремо)")
    resolved = _resolve_date_tokens([d for d, _ in split_tokens], default_year)
    return [(start, end, tm) for (start, end), (_, tm) in zip(resolved, split_tokens)]


def format_schedule(entries: list[ScheduleItem]) -> str:
    if not entries:
        raise ValueError("Порожня дата")
    if all(tm is None for _, _, tm in entries):
        return _format_date_items([(s, e) for s, e, _ in entries])
    parts = []
    for i, (s, e, tm) in enumerate(entries):
        nxt = entries[i + 1] if i + 1 < len(entries) else None
        same_year = nxt is not None and e.year == nxt[1].year
        d_txt = _fmt(s, e, with_month=True, with_year=not same_year)
        parts.append(f"{d_txt} {_fmt_time(*tm)}" if tm is not None else d_txt)
    return join_uk(parts)
