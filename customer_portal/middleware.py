from django.shortcuts import redirect

from core.models import portal_customer

ALLOWED_PREFIXES = ("/klantportaal/", "/accounts/", "/static/")


class CustomerPortalMiddleware:
    """Klantaccounts zien uitsluitend het klantportaal; de rest van het portaal is afgeschermd."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and portal_customer(user) is not None:
            request.portal_customer = portal_customer(user)
            if not request.path.startswith(ALLOWED_PREFIXES):
                return redirect("customer_portal:home")
        return self.get_response(request)
