# (url-naam, label, icoon, recht, badge-sleutel)
NAV = [
    ("Overzicht", [
        ("dashboard", "Dashboard", "grid-1x2", None, None),
    ]),
    ("Zendingen", [
        ("shipments:sea_list", "Zeevracht", "water", "shipments.view_seashipment", "ched"),
        ("shipments:road_list", "Wegtransport", "truck", "shipments.view_roadtransport", None),
        ("documents:list", "Documenten", "file-earmark-text", "documents.view_document", None),
    ]),
    ("Dagelijks", [
        ("meetings:day", "Overleggen", "chat-square-text", "meetings.view_meetingitem", "questions"),
        ("actions:dashboard", "Acties & escalaties", "exclamation-triangle", "actions.view_action", "escalations"),
        ("actions:extracost_list", "Extra kosten", "currency-euro", "actions.view_extracost", None),
    ]),
    ("Planning", [
        ("planning:calendar", "Agenda & rooster", "calendar3", "planning.view_shift", None),
        ("planning:swap_list", "Ruilverzoeken", "arrow-left-right", "planning.view_shift", "swaps"),
        ("planning:employee_list", "Medewerkers", "people", "planning.view_employee", None),
        ("planning:absence_list", "Afwezigheid", "airplane", "planning.view_absence", None),
    ]),
    ("Stamgegevens", [
        ("core:customer_list", "Klanten", "building", "core.view_customer", None),
        ("core:shippingline_list", "Rederijen", "life-preserver", "core.view_shippingline", None),
        ("core:address_list", "Laad-/losadressen", "geo", "core.view_address", None),
        ("core:port_list", "Havens", "geo-alt", "core.view_port", None),
        ("core:terminal_list", "Terminals", "box-seam", "core.view_terminal", None),
        ("core:roadcarrier_list", "Vervoerders", "truck-front", "core.view_roadcarrier", None),
        ("core:inspectionpoint_list", "Keurpunten", "clipboard2-check", "core.view_inspectionpoint", None),
    ]),
    ("Beheer", [
        ("core:user_list", "Accounts & rechten", "person-lock", "auth.view_user", None),
        ("core:auditlog", "Wijzigingslog", "clock-history", "core.view_auditlog", None),
    ]),
]

QUICK_CREATE = [
    ("shipments:seashipment_create", "Zeecontainer", "water", "shipments.add_seashipment"),
    ("shipments:sea_bulk", "Meerdere containers", "stack", "shipments.add_seashipment"),
    ("documents:document_create", "Document uploaden", "upload", "documents.add_document"),
    ("shipments:roadtransport_create", "Wegtransport", "truck", "shipments.add_roadtransport"),
    ("actions:action_create", "Actie / escalatie", "exclamation-triangle", "actions.add_action"),
    ("core:customer_create", "Klant", "building", "core.add_customer"),
]


def _badges(user):
    """Tellers voor in het menu: wat vraagt nu aandacht."""
    from actions.models import Action
    from meetings.models import MeetingItem
    from planning.models import ShiftSwapRequest
    from shipments.models import SeaShipment

    employee = getattr(user, "employee", None)
    badges = {
        "ched": SeaShipment.objects.filter(status__in=SeaShipment.OPEN_STATUSES, inspection_required=True,
                                           inspection_status="aan_te_melden").count(),
        "escalations": Action.objects.filter(status__in=Action.OPEN_STATUSES, kind=Action.KIND_ESCALATION).count(),
        "questions": MeetingItem.objects.filter(status="open", colleagues=employee).count() if employee else 0,
        "swaps": 0,
        "my_actions": Action.objects.filter(status__in=Action.OPEN_STATUSES, owner=employee).count() if employee else 0,
    }
    swaps = ShiftSwapRequest.objects.none()
    if employee:
        swaps = ShiftSwapRequest.objects.filter(colleague=employee, status=ShiftSwapRequest.STATUS_WAIT_COLLEAGUE)
    badges["swaps"] = swaps.count()
    if user.has_perm("planning.generate_roster"):
        badges["swaps"] += ShiftSwapRequest.objects.filter(status=ShiftSwapRequest.STATUS_WAIT_PLANNER).count()
    return badges


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"nav_sections": []}
    if getattr(request, "portal_customer", None) is not None:
        return {"nav_sections": [], "is_portal_customer": True, "customer": request.portal_customer}
    from django.urls import reverse

    badges = _badges(user)
    sections = []
    for title, items in NAV:
        visible = [
            {"url": reverse(url), "label": label, "icon": icon, "badge": badges.get(badge) if badge else None}
            for url, label, icon, perm, badge in items
            if perm is None or user.has_perm(perm)
        ]
        if visible:
            sections.append({"title": title, "items": visible})
    # Het langste menu-item dat met het huidige pad begint is actief.
    path = request.path
    matches = [i for s in sections for i in s["items"] if path == i["url"] or (i["url"] != "/" and path.startswith(i["url"]))]
    if matches:
        max(matches, key=lambda i: len(i["url"]))["active"] = True
    quick = [{"url": reverse(u), "label": label, "icon": icon} for u, label, icon, perm in QUICK_CREATE if user.has_perm(perm)]
    return {"nav_sections": sections, "quick_create": quick, "badges": badges,
            "attention_total": badges["my_actions"] + badges["swaps"] + badges["questions"]}
