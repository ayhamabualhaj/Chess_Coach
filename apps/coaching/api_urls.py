from django.urls import path

from .views.coaching_api_views import ReportDetailAPI, ReportListAPI

urlpatterns = [
    path("reports/", ReportListAPI.as_view(), name="api_report_list"),
    path("reports/<int:report_id>/", ReportDetailAPI.as_view(), name="api_report_detail"),
]