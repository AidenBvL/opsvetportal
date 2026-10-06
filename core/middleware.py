from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

PUBLIC_PREFIXES = ("/accounts/login/", "/static/", "/agenda/ics/", "/admin/login/")


class LoginRequiredMiddleware:
    """Het hele portaal is alleen toegankelijk na inloggen (behalve login en ICS-feeds)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(PUBLIC_PREFIXES):
            return redirect(f"{reverse(settings.LOGIN_URL)}?next={request.path}")
        return self.get_response(request)
