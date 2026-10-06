from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Paaszondag volgens het anonieme Gregoriaanse algoritme."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def dutch_holidays(year: int, include_liberation_day: bool = True):
    """Nederlandse officiële feestdagen als lijst (datum, naam)."""
    easter = easter_sunday(year)
    kingsday = date(year, 4, 27)
    if kingsday.weekday() == 6:
        kingsday = date(year, 4, 26)
    days = [
        (date(year, 1, 1), "Nieuwjaarsdag"),
        (easter - timedelta(days=2), "Goede Vrijdag"),
        (easter, "Eerste Paasdag"),
        (easter + timedelta(days=1), "Tweede Paasdag"),
        (kingsday, "Koningsdag"),
        (easter + timedelta(days=39), "Hemelvaartsdag"),
        (easter + timedelta(days=49), "Eerste Pinksterdag"),
        (easter + timedelta(days=50), "Tweede Pinksterdag"),
        (date(year, 12, 25), "Eerste Kerstdag"),
        (date(year, 12, 26), "Tweede Kerstdag"),
    ]
    if include_liberation_day:
        days.append((date(year, 5, 5), "Bevrijdingsdag"))
    return sorted(days)
