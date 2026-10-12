from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.coaching.services import coaching_service
from apps.coaching.services.coaching_service import CoachingError


@login_required
def coaching_home(request):
    overview = coaching_service.get_overview(request.user)
    return render(request, "coaching/home.html", overview)


@login_required
@require_POST
def create_report(request):
    try:
        report = coaching_service.request_report(request.user, request.POST.getlist("games"))
    except CoachingError as e:
        messages.error(request, str(e))
        return redirect("coaching_home")
    messages.info(request, "The AI coach is studying your games. This page updates by itself.")
    return redirect("report_detail", report_id=report.pk)


@login_required
def report_detail(request, report_id):
    detail = coaching_service.get_report_detail(request.user, report_id)
    if detail is None:
        raise Http404("Report not found")
    return render(request, "coaching/report_detail.html", detail)


@login_required
def report_status(request, report_id):
    report = coaching_service.get_report(request.user, report_id)
    if report is None:
        raise Http404("Report not found")
    return JsonResponse({"status": report.status, "label": report.get_status_display()})