NAV = [
    ("Overzicht", [
        ("dashboard", "Dashboard", "speedometer2", None),
    ]),
    ("Planning", [
        ("planning:calendar", "Agenda & rooster", "calendar3", "planning.view_shift"),
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
    ]),
]


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"nav_sections": []}
    sections = []
    for title, items in NAV:
        visible = [
            {"url_name": url, "label": label, "icon": icon}
            for url, label, icon, perm in items
            if perm is None or user.has_perm(perm)
        ]
        if visible:
            sections.append({"title": title, "items": visible})
    return {"nav_sections": sections}
