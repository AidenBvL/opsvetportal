NAV = [
    ("Overzicht", [
        ("dashboard", "Dashboard", "speedometer2", None),
    ]),
    ("Planning", [
        ("planning:calendar", "Agenda & rooster", "calendar3", "planning.view_shift"),
        ("planning:swap_list", "Ruilverzoeken", "arrow-left-right", "planning.view_shift"),
        ("planning:employee_list", "Medewerkers", "people", "planning.view_employee"),
        ("planning:absence_list", "Afwezigheid", "airplane", "planning.view_absence"),
    ]),
    ("Dagelijks", [
        ("meetings:day", "Overleggen", "chat-square-text", "meetings.view_meetingitem"),
        ("actions:dashboard", "Acties & escalaties", "exclamation-triangle", "actions.view_action"),
        ("actions:extracost_list", "Extra kosten", "currency-euro", "actions.view_extracost"),
    ]),
    ("Zendingen", [
        ("shipments:sea_list", "Zeevracht", "water", "shipments.view_seashipment"),
        ("shipments:road_list", "Wegtransport", "truck", "shipments.view_roadtransport"),
        ("documents:list", "Documenten", "file-earmark-text", "documents.view_document"),
    ]),
    ("Stamgegevens", [
        ("core:customer_list", "Klanten", "building", "core.view_customer"),
        ("core:shippingline_list", "Rederijen", "life-preserver", "core.view_shippingline"),
        ("core:roadcarrier_list", "Vervoerders", "truck-front", "core.view_roadcarrier"),
        ("core:inspectionpoint_list", "Keurpunten", "clipboard2-check", "core.view_inspectionpoint"),
    ]),
    ("Beheer", [
        ("core:user_list", "Accounts & rechten", "person-lock", "auth.view_user"),
        ("core:auditlog", "Wijzigingslog", "clock-history", "core.view_auditlog"),
    ]),
]


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"nav_sections": []}
    if getattr(request, "portal_customer", None) is not None:
        return {"nav_sections": [], "is_portal_customer": True, "customer": request.portal_customer}
    from django.urls import reverse

    sections = []
    for title, items in NAV:
        visible = [
            {"url": reverse(url), "label": label, "icon": icon}
            for url, label, icon, perm in items
            if perm is None or user.has_perm(perm)
        ]
        if visible:
            sections.append({"title": title, "items": visible})
    # Het langste menu-item dat met het huidige pad begint is actief.
    path = request.path
    matches = [i for s in sections for i in s["items"] if path == i["url"] or (i["url"] != "/" and path.startswith(i["url"]))]
    if matches:
        max(matches, key=lambda i: len(i["url"]))["active"] = True
    return {"nav_sections": sections}
