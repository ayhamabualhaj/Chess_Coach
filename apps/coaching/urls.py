from django.urls import path

from .views.coaching_api_views import ReportStatusAPI
from .views.coaching_views import coaching_home, create_report, report_detail, toggle_practice

urlpatterns = [
    path("", coaching_home, name="coaching_home"),
    path("reports/new/", create_report, name="create_report"),
    path("reports/<int:report_id>/", report_detail, name="report_detail"),
    path("reports/<int:report_id>/status/", ReportStatusAPI.as_view(), name="report_status"),
    path("reports/<int:report_id>/practice/<int:index>/", toggle_practice, name="toggle_practice"),
]