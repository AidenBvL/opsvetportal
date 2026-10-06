"""Automatische generator voor het thuiswerk- en dienstrooster.

De logica staat los van de database (pure dataclasses), zodat hij goed te testen is.
`planning.services` vertaalt de modellen naar deze structuren en schrijft het resultaat terug.

Spelregels (overgenomen uit het oorspronkelijke Excel-rooster):

Thuiswerken
  1. Iedere deelnemer krijgt een vast aantal thuiswerkdagen per week (standaard 1).
  2. Collega's uit dezelfde afdelingsgroep werken nooit op dezelfde dag thuis en ook nooit
     op de dag direct na de thuiswerkdag van een groepsgenoot.
  3. Een vaste vrije dag (bijv. woensdag bij een 4-daagse week) is nooit een thuiswerkdag.
  4. Voorkeursdagen en het patroon van de vorige maand worden zoveel mogelijk aangehouden;
     daarnaast wordt de bezetting op kantoor zo gelijk mogelijk over de week verdeeld.

Diensten (avonddienst ma-vr, zaterdagdienst)
  5. Precies 1 persoon per dienst, en nooit twee dagen achter elkaar dezelfde persoon.
  6. Wie zaterdag dienst heeft, heeft in de voorafgaande werkweek (ma-vr) geen avonddienst.
  7. Persoonlijke uitsluitingen worden altijd gerespecteerd (bijv. Aiden: nooit op maandag,
     want schooldag), net als vrije dagen, afwezigheid en feestdagen.
  8. Waar mogelijk krijgt een thuiswerker op zijn thuiswerkdag ook de avonddienst.
  9. Diensten worden eerlijk verdeeld en de toewijzing aan weekdagen rouleert, zodat
     niemand structureel op dezelfde weekdag dienst heeft.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

EVENING = "avond"
SATURDAY = "zaterdag"
WORKDAYS = range(5)

# Gewichten van de kostenfunctie voor diensten.
COST_SECOND_SHIFT_SAME_WEEK = 1000
COST_CONSECUTIVE_DAY = 5000  # alleen gebruikt als de harde regel onhaalbaar is
COST_FAIRNESS = 10
COST_SAME_WEEKDAY = 6
BONUS_WFH = 8
SEARCH_NODE_LIMIT = 200_000


@dataclass
class Person:
    id: int
    name: str
    groups: frozenset = frozenset()
    wfh_days: int = 1
    preferred_wfh: frozenset = frozenset()
    days_off: frozenset = frozenset()
    in_pool: bool = False
    no_shift_weekdays: frozenset = frozenset()
    unavailable: frozenset = frozenset()

    def is_available(self, day: date) -> bool:
        return day not in self.unavailable and day.weekday() not in self.days_off

    def can_take_shift(self, day: date) -> bool:
        return self.in_pool and self.is_available(day) and day.weekday() not in self.no_shift_weekdays


@dataclass
class RosterResult:
    wfh_pattern: dict = field(default_factory=dict)  # person_id -> frozenset(weekdagen)
    wfh: dict = field(default_factory=dict)  # date -> set(person_id)
    shifts: dict = field(default_factory=dict)  # (date, type) -> person_id | None
    warnings: list = field(default_factory=list)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def daterange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


# ---------------------------------------------------------------------------
# Thuiswerken
# ---------------------------------------------------------------------------


def _conflicts(days_a, days_b, strict: bool) -> bool:
    """Twee groepsgenoten mogen niet dezelfde dag of (strict) aangrenzende dagen hebben."""
    limit = 1 if strict else 0
    return any(abs(a - b) <= limit for a in days_a for b in days_b)


def solve_wfh_pattern(people, previous: dict | None = None):
    """Bepaal per persoon een vast weekpatroon van thuiswerkdagen.

    Geeft (patroon, waarschuwingen) terug; patroon = {person_id: frozenset(weekdagen)}.
    """
    previous = previous or {}
    participants = [p for p in people if p.wfh_days > 0]
    warnings = []

    options = {}
    for p in participants:
        allowed = [d for d in WORKDAYS if d not in p.days_off]
        k = min(p.wfh_days, len(allowed))
        if k < p.wfh_days:
            warnings.append(f"{p.name}: te weinig werkdagen voor {p.wfh_days} thuiswerkdagen.")
        combos = [frozenset(c) for c in itertools.combinations(allowed, k)]
        target = p.preferred_wfh or previous.get(p.id) or frozenset()
        weight = 10 if p.preferred_wfh else 3

        def own_cost(combo, target=target, weight=weight):
            cost = weight * len(combo - target) if target else 0
            # Meerdere eigen thuiswerkdagen liever niet aan elkaar vast.
            cost += sum(2 for a in combo for b in combo if b == a + 1)
            return cost

        options[p.id] = sorted(combos, key=own_cost), own_cost

    by_id = {p.id: p for p in participants}

    def neighbours(pid):
        groups = by_id[pid].groups
        return [q.id for q in participants if q.id != pid and groups & q.groups]

    # Meest beperkte personen eerst: veel groepsgenoten en weinig opties.
    order = sorted(participants, key=lambda p: (-len(neighbours(p.id)), len(options[p.id][0]), p.name))

    def search(strict: bool):
        best = {"cost": None, "assignment": None}
        nodes = 0
        assignment = {}
        load = [0] * 5

        def rec(i, cost):
            nonlocal nodes
            nodes += 1
            if nodes > SEARCH_NODE_LIMIT:
                return
            if best["cost"] is not None and cost >= best["cost"]:
                return
            if i == len(order):
                best["cost"], best["assignment"] = cost, dict(assignment)
                return
            person = order[i]
            combos, own_cost = options[person.id]
            for combo in combos:
                if any(
                    _conflicts(combo, assignment[q], strict) for q in neighbours(person.id) if q in assignment
                ):
                    continue
                # Kantoorbezetting gelijk verdelen: kwadratische kosten op aantal thuiswerkers per dag.
                extra = own_cost(combo) + sum(2 * load[d] + 1 for d in combo)
                assignment[person.id] = combo
                for d in combo:
                    load[d] += 1
                rec(i + 1, cost + extra)
                for d in combo:
                    load[d] -= 1
                del assignment[person.id]

        rec(0, 0)
        return best["assignment"]

    result = search(strict=True)
    if result is None:
        warnings.append(
            "Geen indeling mogelijk waarbij groepsgenoten nooit op opvolgende dagen thuiswerken; "
            "die regel is versoepeld (wel nooit op dezelfde dag)."
        )
        result = search(strict=False)
    if result is None:
        warnings.append("Geen geldige thuiswerkindeling gevonden; voorkeurs-/eerste opties gebruikt.")
        result = {p.id: options[p.id][0][0] for p in participants if options[p.id][0]}
    return result, warnings


def expand_wfh(people, pattern, start: date, end: date, holidays=frozenset()):
    """Zet het weekpatroon om naar concrete datums binnen [start, end]."""
    by_id = {p.id: p for p in people}
    wfh = defaultdict(set)
    for day in daterange(start, end):
        if day.weekday() >= 5 or day in holidays:
            continue
        for pid, days in pattern.items():
            if day.weekday() in days and by_id[pid].is_available(day):
                wfh[day].add(pid)
    return dict(wfh)


# ---------------------------------------------------------------------------
# Diensten
# ---------------------------------------------------------------------------


class _Stats:
    def __init__(self, history):
        self.total = defaultdict(int)
        self.weekday = defaultdict(lambda: defaultdict(int))
        self.saturdays = defaultdict(int)
        self.last_saturday = {}
        for (day, kind), pid in sorted(history.items(), key=lambda item: item[0][0]):
            if pid is not None:
                self.add(pid, day, kind)

    def add(self, pid, day, kind):
        self.total[pid] += 1
        if kind == SATURDAY:
            self.saturdays[pid] += 1
            self.last_saturday[pid] = max(day, self.last_saturday.get(pid, day))
        else:
            self.weekday[pid][day.weekday()] += 1


def plan_shifts(people, start: date, end: date, wfh=None, history=None, holidays=frozenset()):
    """Plan avond- en zaterdagdiensten tussen start en end (inclusief).

    `history` bevat diensten die vastliggen: uit eerdere periodes en handmatig
    vastgezette diensten binnen de periode. Die worden nooit overschreven.
    Geeft (shifts, waarschuwingen) terug; shifts = {(datum, type): person_id | None}.
    """
    wfh = wfh or {}
    fixed = dict(history or {})
    pool = sorted((p for p in people if p.in_pool), key=lambda p: p.name)
    pool_order = {p.id: i for i, p in enumerate(pool)}
    stats = _Stats({k: v for k, v in fixed.items() if k[0] < start})
    # Vastgezette diensten binnen de periode tellen ook mee voor de eerlijke verdeling.
    for (day, kind), pid in fixed.items():
        if start <= day <= end and pid is not None:
            stats.add(pid, day, kind)

    planned = {}
    warnings = []

    def who(day, kind=EVENING):
        key = (day, kind)
        return planned.get(key, fixed.get(key))

    monday = week_start(start)
    while monday <= end:
        weekdays = [monday + timedelta(days=i) for i in WORKDAYS]
        saturday = monday + timedelta(days=5)
        open_days = [
            d for d in weekdays if start <= d <= end and d not in holidays and (d, EVENING) not in fixed
        ]
        needs_saturday = start <= saturday <= end and saturday not in holidays and (saturday, SATURDAY) not in fixed

        evening_people_fixed = {fixed[(d, EVENING)] for d in weekdays if (d, EVENING) in fixed}

        sat_candidates = [None]
        if needs_saturday:
            cands = [p for p in pool if p.can_take_shift(saturday) and p.id not in evening_people_fixed]
            cands.sort(
                key=lambda p: (
                    stats.saturdays[p.id],
                    stats.last_saturday.get(p.id, date.min),
                    stats.total[p.id],
                    pool_order[p.id],
                )
            )
            sat_candidates = [p.id for p in cands] or [None]
            if not cands:
                warnings.append(f"Geen beschikbare medewerker voor de zaterdagdienst van {saturday:%d-%m-%Y}.")
        sat_fixed = fixed.get((saturday, SATURDAY))

        chosen = None
        for sat_pid in sat_candidates:
            blocked = sat_pid if needs_saturday else sat_fixed
            assignment = _solve_week(open_days, pool, blocked, who, stats, wfh, fixed, strict=True)
            if assignment is not None:
                chosen = (sat_pid, assignment)
                break
        if chosen is None:
            sat_pid = sat_candidates[0]
            blocked = sat_pid if needs_saturday else sat_fixed
            assignment = _solve_week(open_days, pool, blocked, who, stats, wfh, fixed, strict=False)
            chosen = (sat_pid, assignment or {})
            if open_days:
                warnings.append(
                    f"Week van {monday:%d-%m}: harde regels niet volledig haalbaar, "
                    "controleer de diensten (mogelijk 2 dagen achter elkaar dezelfde persoon)."
                )

        sat_pid, assignment = chosen
        for day in open_days:
            pid = assignment.get(day)
            planned[(day, EVENING)] = pid
            if pid is None:
                warnings.append(f"Geen beschikbare medewerker voor de avonddienst van {day:%d-%m-%Y}.")
            else:
                stats.add(pid, day, EVENING)
        if needs_saturday:
            planned[(saturday, SATURDAY)] = sat_pid
            if sat_pid is not None:
                stats.add(sat_pid, saturday, SATURDAY)

        monday += timedelta(days=7)

    return planned, warnings


def _solve_week(days, pool, blocked_pid, who, stats, wfh, fixed, strict):
    """Kies voor elke open avond in de week een persoon met minimale kosten (branch & bound)."""
    if not days:
        return {}
    week_counts = defaultdict(int)
    for d in (days[0] - timedelta(days=days[0].weekday()) + timedelta(days=i) for i in WORKDAYS):
        pid = fixed.get((d, EVENING))
        if pid is not None:
            week_counts[pid] += 1

    candidates = {}
    for day in days:
        cands = [p.id for p in pool if p.can_take_shift(day) and p.id != blocked_pid]
        candidates[day] = cands or [None]

    best = {"cost": None, "assignment": None}
    nodes = 0
    assignment = {}
    extra_total = defaultdict(int)

    def person_on(day):
        if day in assignment:
            return assignment[day]
        return who(day)

    def rec(i, cost):
        nonlocal nodes
        nodes += 1
        if nodes > SEARCH_NODE_LIMIT:
            return
        if best["cost"] is not None and cost >= best["cost"]:
            return
        if i == len(days):
            best["cost"], best["assignment"] = cost, dict(assignment)
            return
        day = days[i]
        prev_pid = person_on(day - timedelta(days=1))
        next_pid = fixed.get((day + timedelta(days=1), EVENING))
        for pid in candidates[day]:
            # Elke dag krijgt precies één stap; de constante BONUS_WFH houdt elke stap >= 0,
            # zodat de branch-and-bound-afkap geldig blijft.
            step = BONUS_WFH
            if pid is None:
                step = 100_000
            else:
                if pid in (prev_pid, next_pid):
                    if strict:
                        continue
                    step += COST_CONSECUTIVE_DAY
                step += COST_SECOND_SHIFT_SAME_WEEK * week_counts[pid]
                total = stats.total[pid] + extra_total[pid]
                step += COST_FAIRNESS * (2 * total + 1)
                step += COST_SAME_WEEKDAY * stats.weekday[pid][day.weekday()]
                if pid in wfh.get(day, ()):
                    step -= BONUS_WFH
            assignment[day] = pid
            if pid is not None:
                week_counts[pid] += 1
                extra_total[pid] += 1
            rec(i + 1, cost + step)
            if pid is not None:
                week_counts[pid] -= 1
                extra_total[pid] -= 1
            del assignment[day]

    rec(0, 0)
    return best["assignment"]


def generate(people, start: date, end: date, history=None, holidays=frozenset(), previous_pattern=None, fixed_wfh=None):
    """Genereer het complete rooster (thuiswerken + diensten) voor een periode."""
    result = RosterResult()
    pattern, warnings = solve_wfh_pattern(people, previous_pattern)
    result.wfh_pattern = pattern
    result.warnings.extend(warnings)
    wfh = expand_wfh(people, pattern, start, end, holidays)
    for day, pids in (fixed_wfh or {}).items():
        wfh.setdefault(day, set()).update(pids)
    result.wfh = wfh
    shifts, warnings = plan_shifts(people, start, end, wfh=wfh, history=history, holidays=holidays)
    result.shifts = shifts
    result.warnings.extend(warnings)
    return result
