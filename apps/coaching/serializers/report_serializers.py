"""Serializers for coaching reports (Django REST Framework)."""
from rest_framework import serializers

from apps.coaching.models import WeaknessReport


class ReportStatusSerializer(serializers.ModelSerializer):
    """The status of a report; the report page asks for it while the AI works."""

    label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = WeaknessReport
        fields = ["status", "label"]


class ReportSerializer(serializers.ModelSerializer):
    """A report in a list."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    games = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = WeaknessReport
        fields = ["id", "status", "status_label", "games", "games_count", "moves_count", "ai_model", "created_at"]
        read_only_fields = fields


class ReportDetailSerializer(ReportSerializer):
    """A full report: the agent's answer, how it got there, and the practice list."""

    practice = serializers.SerializerMethodField()

    class Meta(ReportSerializer.Meta):
        fields = [
            *ReportSerializer.Meta.fields, "error", "summary", "weaknesses",
            "turns", "seconds", "input_tokens", "output_tokens", "tool_calls", "practice",
        ]
        read_only_fields = fields

    def get_practice(self, report) -> list:
        plan = self.context.get("plan")
        return plan.tasks if plan else []


class CreateReportSerializer(serializers.Serializer):
    """Input for a new report: the ids of the games the coach should study."""

    games = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)