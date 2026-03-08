from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from .utils import user_is_staff_admin


def staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if not user_is_staff_admin(request.user):
            messages.error(request, "You do not have permission to access Admin Console.")
            return redirect("core:home")
        return view_func(request, *args, **kwargs)

    return _wrapped
