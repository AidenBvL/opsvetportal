from collections import Counter
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from .generator import EVENING, SATURDAY, Person, generate, plan_shifts, solve_wfh_pattern
from .holidays import dutch_holidays, easter_sunday
from .models import Absence, Employee, Holiday, Shift, WorkFromHomeDay
from .services import generate_month

F = frozenset


def team():
    return [
        Person(1, "Rob", F({"Sales"})),
        Person(2, "Andy", F({"Transport"}), in_pool=True),
        Person(3, "Marco", F({"Sales", "Fresh"})),
        Person(4, "Thomas", F({"Transport"})),
        Person(5, "Desley", F({"Fresh"}), days_off=F({2}), in_pool=True),
        Person(6, "Davy", F({"OPS"})),
        Person(7, "Dominic", F({"VET"}), in_pool=True),
        Person(8, "Jarno", F({"VET"}), wfh_days=2),
        Person(9, "Raymond", F({"Management"}), in_pool=True),
        Person(10, "Mitchell", F({"Management"}), in_pool=True),
        Person(11, "Aiden", F(), wfh_days=0, in_pool=True, no_shift_weekdays=F({0})),
    ]


def assert_shift_rules(test, people, shifts):
    by_id = {p.id: p for p in people}
    by_day = {day: pid for (day, kind), pid in shifts.items()}
    for (day, kind), pid in shifts.items():
        test.assertIsNotNone(pid, f"Dienst {day} niet ingevuld")
        p = by_id[pid]
        test.assertTrue(p.in_pool)
        test.assertNotIn(day.weekday(), p.no_shift_weekdays, f"{p.name} heeft dienst op uitgesloten dag {day}")
        test.assertNotIn(day.weekday(), p.days_off, f"{p.name} heeft dienst op vrije dag {day}")
        test.assertNotIn(day, p.unavailable)
        test.assertEqual(kind, SATURDAY if day.weekday() == 5 else EVENING)
        test.assertNotEqual(by_day.get(day - timedelta(days=1)), pid, f"{p.name} twee dagen achter elkaar ({day})")
        if kind == SATURDAY:
            monday = day - timedelta(days=5)
            week = [by_day.get(monday + timedelta(days=i)) for i in range(5)]
            test.assertNotIn(pid, week, f"{p.name} zaterdag {day} maar ook avonddienst die week")


class WfhPatternTests(TestCase):
    def test_group_members_never_same_or_adjacent_day(self):
        people = team()
        pattern, warnings = solve_wfh_pattern(people)
        self.assertEqual(warnings, [])
        by_id = {p.id: p for p in people}
        for a, days_a in pattern.items():
            for b, days_b in pattern.items():
                if a >= b or not (by_id[a].groups & by_id[b].groups):
                    continue
                for da in days_a:
                    for db in days_b:
                        self.assertGreater(abs(da - db), 1, f"{by_id[a].name}/{by_id[b].name}")

    def test_days_counts_and_exclusions(self):
        people = team()
        pattern, _ = solve_wfh_pattern(people)
        self.assertNotIn(11, pattern)  # Aiden doet niet mee
        self.assertEqual(len(pattern[8]), 2)  # Jarno 2 dagen
        self.assertNotIn(2, pattern[5])  # Desley nooit op woensdag
        for pid, days in pattern.items():
            self.assertTrue(all(d < 5 for d in days))

    def test_preferences_are_respected_when_possible(self):
        people = team()
        people[0].preferred_wfh = F({0})  # Rob maandag
        people[4].preferred_wfh = F({4})  # Desley vrijdag
        pattern, _ = solve_wfh_pattern(people)
        self.assertEqual(pattern[1], F({0}))
        self.assertEqual(pattern[5], F({4}))

    def test_relaxes_when_impossible(self):
        people = [Person(i, f"P{i}", F({"X"})) for i in range(4)]
        pattern, warnings = solve_wfh_pattern(people)
        self.assertTrue(warnings)
        days = [next(iter(d)) for d in pattern.values()]
        self.assertEqual(len(days), len(set(days)))  # nooit dezelfde dag


class ShiftPlanTests(TestCase):
    def test_october_2026_rules(self):
        people = team()
        result = generate(people, date(2026, 10, 1), date(2026, 10, 31))
        assert_shift_rules(self, people, result.shifts)
        self.assertEqual(len(result.shifts), 27)  # 22 werkdagen + 5 zaterdagen
        aiden_days = [d for (d, _), pid in result.shifts.items() if pid == 11]
        self.assertTrue(aiden_days)
        self.assertFalse([d for d in aiden_days if d.weekday() == 0])

    def test_fair_distribution_over_several_months(self):
        people = team()
        history = {}
        for month in range(9, 13):
            start = date(2026, month, 1)
            end = (date(2026, month + 1, 1) if month < 12 else date(2027, 1, 1)) - timedelta(days=1)
            result = generate(people, start, end, history=history)
            history.update(result.shifts)
        assert_shift_rules(self, people, history)
        counts = Counter(history.values())
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 2, counts)
        saturdays = Counter(pid for (d, k), pid in history.items() if k == SATURDAY)
        self.assertLessEqual(max(saturdays.values()) - min(saturdays.values()), 1, saturdays)
        # Rotatie: niemand meer dan de helft van zijn avonddiensten op dezelfde weekdag.
        for pid in counts:
            per_weekday = Counter(d.weekday() for (d, k), p in history.items() if p == pid and k == EVENING)
            self.assertLessEqual(max(per_weekday.values()), max(2, sum(per_weekday.values()) // 2), per_weekday)

    def test_wfh_person_gets_evening_shift_when_possible(self):
        people = team()
        result = generate(people, date(2026, 10, 1), date(2026, 10, 31))
        linked = sum(1 for (d, k), pid in result.shifts.items() if pid in result.wfh.get(d, ()))
        self.assertGreaterEqual(linked, 4)

    def test_month_boundary_saturday_rule_uses_history(self):
        people = team()
        # Andy had avonddienst op ma 28 september; za 3 oktober mag hij dus niet.
        history = {(date(2026, 9, 28), EVENING): 2, (date(2026, 9, 29), EVENING): 7, (date(2026, 9, 30), EVENING): 9}
        shifts, _ = plan_shifts(people, date(2026, 10, 1), date(2026, 10, 31), history=history)
        self.assertNotIn(shifts[(date(2026, 10, 3), SATURDAY)], {2, 7, 9})
        self.assertNotEqual(shifts[(date(2026, 10, 1), EVENING)], 9)  # niet na 30 sept dezelfde

    def test_absence_and_holidays(self):
        people = team()
        andy = people[1]
        andy.unavailable = F(date(2026, 12, d) for d in range(1, 32))
        holidays = F({date(2026, 12, 25), date(2026, 12, 26)})
        result = generate(people, date(2026, 12, 1), date(2026, 12, 31), holidays=holidays)
        self.assertNotIn(2, result.shifts.values())
        self.assertNotIn((date(2026, 12, 25), EVENING), result.shifts)
        self.assertNotIn((date(2026, 12, 26), SATURDAY), result.shifts)
        assert_shift_rules(self, people, result.shifts)

    def test_fixed_shifts_are_kept(self):
        people = team()
        fixed = {(date(2026, 10, 7), EVENING): 10}
        shifts, _ = plan_shifts(people, date(2026, 10, 1), date(2026, 10, 31), history=fixed)
        self.assertNotIn((date(2026, 10, 7), EVENING), shifts)  # niet overschreven
        self.assertNotEqual(shifts[(date(2026, 10, 6), EVENING)], 10)
        self.assertNotEqual(shifts[(date(2026, 10, 8), EVENING)], 10)

    def test_warns_when_nobody_available(self):
        people = [Person(1, "Aiden", in_pool=True, no_shift_weekdays=F({0}), wfh_days=0)]
        shifts, warnings = plan_shifts(people, date(2026, 10, 5), date(2026, 10, 5))
        self.assertIsNone(shifts[(date(2026, 10, 5), EVENING)])
        self.assertTrue(warnings)


class HolidayTests(TestCase):
    def test_easter(self):
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        self.assertEqual(easter_sunday(2027), date(2027, 3, 28))

    def test_kingsday_on_sunday_moves(self):
        names = dict((n, d) for d, n in dutch_holidays(2025))
        self.assertEqual(names["Koningsdag"], date(2025, 4, 26))


class RosterServiceTests(TestCase):
    def setUp(self):
        call_command("seed_portal", verbosity=0, stdout=open("/dev/null", "w"))

    def test_generate_month_in_database(self):
        generate_month(2026, 10)
        aiden = Employee.objects.get(name="Aiden")
        self.assertFalse(Shift.objects.filter(employee=aiden, date__week_day=2).exists())  # 2 = maandag in Django
        self.assertFalse(WorkFromHomeDay.objects.filter(employee=aiden).exists())
        self.assertEqual(Shift.objects.filter(date__month=10).count(), 27)
        for shift in Shift.objects.filter(linked_to_wfh=True):
            self.assertTrue(WorkFromHomeDay.objects.filter(employee=shift.employee, date=shift.date).exists())

    def test_regenerate_keeps_manual_changes_and_absence(self):
        generate_month(2026, 10)
        mitchell = Employee.objects.get(name="Mitchell De Jong")
        shift = Shift.objects.get(date=date(2026, 10, 14))
        shift.employee, shift.is_manual = mitchell, True
        shift.save()
        andy = Employee.objects.get(name="Andy Salihi")
        Absence.objects.create(employee=andy, start_date=date(2026, 10, 19), end_date=date(2026, 10, 23))
        generate_month(2026, 10)
        self.assertEqual(Shift.objects.get(date=date(2026, 10, 14)).employee, mitchell)
        self.assertFalse(Shift.objects.filter(employee=andy, date__range=(date(2026, 10, 19), date(2026, 10, 23))).exists())
        self.assertFalse(WorkFromHomeDay.objects.filter(employee=andy, date__range=(date(2026, 10, 19), date(2026, 10, 23))).exists())
        self.assertFalse(Shift.objects.filter(date=date(2026, 10, 13), employee=mitchell).exists())

    def test_holiday_in_db_skipped(self):
        self.assertTrue(Holiday.objects.filter(date=date(2026, 12, 25)).exists())
        generate_month(2026, 12)
        self.assertFalse(Shift.objects.filter(date=date(2026, 12, 25)).exists())


class PlanningViewTests(TestCase):
    def setUp(self):
        call_command("seed_portal", verbosity=0, stdout=open("/dev/null", "w"))
        self.user = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(self.user)

    def test_generate_and_toggle_via_views(self):
        r = self.client.post("/agenda/genereren/", {"jaar": 2026, "maand": 11})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Shift.objects.filter(date__month=11).exists())
        rob = Employee.objects.get(name="Rob Goldenbelt")
        self.client.post("/agenda/thuiswerk/wissel/", {"employee": rob.pk, "date": "2026-11-11"})
        self.assertTrue(WorkFromHomeDay.objects.get(employee=rob, date=date(2026, 11, 11)).is_manual)

    def test_locked_roster_is_not_regenerated(self):
        self.client.post("/agenda/genereren/", {"jaar": 2026, "maand": 11})
        self.client.post("/agenda/status/", {"jaar": 2026, "maand": 11, "status": "definitief"})
        before = list(Shift.objects.filter(date__month=11).values_list("employee_id", flat=True))
        Shift.objects.filter(date__month=11).delete()
        self.client.post("/agenda/genereren/", {"jaar": 2026, "maand": 11})
        self.assertFalse(Shift.objects.filter(date__month=11).exists())
        self.assertTrue(before)

    def test_manual_shift_edit_warns_for_aiden_monday(self):
        aiden = Employee.objects.get(name="Aiden")
        r = self.client.post("/agenda/dienst/2026-10-12/", {"employee": aiden.pk, "note": ""}, follow=True)
        self.assertContains(r, "nooit dienst op deze weekdag")
        self.assertTrue(Shift.objects.get(date=date(2026, 10, 12)).is_manual)

    def test_ics_feed(self):
        generate_month(2026, 10)
        e = Shift.objects.first().employee
        self.client.logout()
        r = self.client.get(f"/agenda/ics/{e.calendar_token}.ics")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"BEGIN:VEVENT", r.content)


class SwapTests(TestCase):
    def setUp(self):
        from django.core import mail  # noqa: F401

        self.andy_user = User.objects.create_user("andy", email="andy@example.com", password="pw")
        self.mitchell_user = User.objects.create_user("mitchell", email="mitchell@example.com", password="pw")
        self.planner = User.objects.create_superuser("raymond", "raymond@example.com", "pw")
        self.andy = Employee.objects.create(name="Andy Salihi", user=self.andy_user)
        self.mitchell = Employee.objects.create(name="Mitchell De Jong", user=self.mitchell_user)
        self.shift = Shift.objects.create(date=date(2030, 10, 8), shift_type=EVENING, employee=self.andy)
        self.other = Shift.objects.create(date=date(2030, 10, 10), shift_type=EVENING, employee=self.mitchell)

    def test_full_swap_flow(self):
        from django.core import mail

        from .models import ShiftSwapRequest

        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            self.client.force_login(self.andy_user)
            with self.captureOnCommitCallbacks(execute=True):
                r = self.client.post(f"/agenda/ruilen/dienst/{self.shift.pk}/", {"colleague": self.mitchell.pk, "colleague_shift": self.other.pk, "message": "tandarts"})
            self.assertEqual(r.status_code, 302)
            swap = ShiftSwapRequest.objects.get()
            self.assertEqual(mail.outbox[-1].to, ["mitchell@example.com"])

            # Andy mag zijn eigen verzoek niet accepteren
            self.client.post(f"/agenda/ruilen/{swap.pk}/", {"action": "accept"})
            swap.refresh_from_db()
            self.assertEqual(swap.status, "wacht_collega")

            self.client.force_login(self.mitchell_user)
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(f"/agenda/ruilen/{swap.pk}/", {"action": "accept"})
            swap.refresh_from_db()
            self.assertEqual(swap.status, "wacht_planner")
            self.assertIn(["raymond@example.com"], [m.to for m in mail.outbox])

            # Mitchell is geen planner
            self.client.post(f"/agenda/ruilen/{swap.pk}/", {"action": "approve"})
            swap.refresh_from_db()
            self.assertEqual(swap.status, "wacht_planner")

            self.client.force_login(self.planner)
            page = self.client.get("/agenda/ruilen/")
            self.assertContains(page, "Ter goedkeuring")
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(f"/agenda/ruilen/{swap.pk}/", {"action": "approve", "note": "ok"})
            self.shift.refresh_from_db()
            self.other.refresh_from_db()
            self.assertEqual((self.shift.employee, self.other.employee), (self.mitchell, self.andy))
            self.assertTrue(self.shift.is_manual and self.other.is_manual)
            self.assertEqual(ShiftSwapRequest.objects.get().status, "goedgekeurd")

    def test_cannot_request_for_someone_elses_shift(self):
        self.client.force_login(self.mitchell_user)
        r = self.client.post(f"/agenda/ruilen/dienst/{self.shift.pk}/", {"colleague": self.andy.pk})
        self.assertRedirects(r, "/agenda/ruilen/", fetch_redirect_response=False)
        from .models import ShiftSwapRequest

        self.assertFalse(ShiftSwapRequest.objects.exists())

    def test_preview_shows_rule_conflicts(self):
        from . import swaps
        from .models import ShiftSwapRequest

        Shift.objects.create(date=date(2030, 10, 9), shift_type=EVENING, employee=self.mitchell)
        swap = ShiftSwapRequest(shift=self.shift, requester=self.andy, colleague=self.mitchell)
        self.assertTrue(any("aangrenzende" in i for i in swaps.preview_issues(swap)))
