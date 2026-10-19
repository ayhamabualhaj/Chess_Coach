"""JSON API for coaching reports (Django REST Framework)."""
from django.http import Http404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.coaching.serializers import (
    CreateReportSerializer, ReportDetailSerializer, ReportSerializer, ReportStatusSerializer,
)
from apps.coaching.services import coaching_service
from apps.coaching.services.coaching_service import ReportLimitError, ReportRequestError


class ReportListAPI(generics.ListCreateAPIView):
    """GET /api/reports/  – the user's reports.
    POST /api/reports/ {"games": [1, 2]}  – ask the AI coach for a new report."""

    serializer_class = ReportSerializer

    def get_queryset(self):
        return coaching_service.list_reports(self.request.user)

    def create(self, request, *args, **kwargs):
        # The serializer checks the input; the service checks the rules.
        incoming = CreateReportSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        try:
            report = coaching_service.request_report(request.user, incoming.validated_data["games"])
        except ReportLimitError as e:
            return Response({"detail": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ReportRequestError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReportSerializer(report).data, status=status.HTTP_202_ACCEPTED)


class ReportDetailAPI(APIView):
    """GET /api/reports/<id>/  – the full report with weaknesses and practice list."""

    def get(self, request, report_id):
        found = coaching_service.get_report_with_plan(request.user, report_id)
        if found is None:
            raise Http404("Report not found")
        return Response(ReportDetailSerializer(found["report"], context={"plan": found["plan"]}).data)


class ReportStatusAPI(APIView):
    """GET /coaching/reports/<id>/status/  – the report page asks this while the AI works."""

    def get(self, request, report_id):
        report = coaching_service.get_report(request.user, report_id)
        if report is None:
            raise Http404("Report not found")
        return Response(ReportStatusSerializer(report).data)