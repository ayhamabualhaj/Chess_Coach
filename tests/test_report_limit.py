"""The daily report limit (MAX_REPORTS_PER_DAY) on the web page and on the API."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.coaching.models import WeaknessReport
from tests.test_api import ApiTestBase
from tests.test_coaching import DUMMY_TASKS, CoachingTestBase

User = get_user_model()


def finished_report(user, hours_ago: float = 0) -> WeaknessReport:
    report = WeaknessReport.objects.create(user=user, status=WeaknessReport.Status.DONE)
    if hours_ago:
        # created_at is set automatically on create, so it is moved back with update().
        WeaknessReport.objects.filter(pk=report.pk).update(created_at=timezone.now() - timedelta(hours=hours_ago))
    return report


@override_settings(TASKS=DUMMY_TASKS, MAX_REPORTS_PER_DAY=2)
class ReportLimitPageTests(CoachingTestBase):
    def test_limit_reached_refuses_a_new_report(self):
        finished_report(self.user)
        finished_report(self.user)
        response = self.client.post(reverse("create_report"), self.choose(), follow=True)
        self.assertContains(response, "Report limit reached (2 in 24 hours)")
        self.assertEqual(WeaknessReport.objects.count(), 2)

    def test_reports_older_than_24_hours_do_not_count(self):
        finished_report(self.user, hours_ago=25)
        finished_report(self.user, hours_ago=30)
        finished_report(self.user)
        self.client.post(reverse("create_report"), self.choose())
        self.assertEqual(WeaknessReport.objects.count(), 4)

    def test_other_users_reports_do_not_count(self):
        other = User.objects.create_user("other", password="pass12345")
        finished_report(other)
        finished_report(other)
        self.client.post(reverse("create_report"), self.choose())
        self.assertEqual(WeaknessReport.objects.filter(user=self.user).count(), 1)


@override_settings(TASKS=DUMMY_TASKS, AI_API_KEY="test-key", MAX_REPORTS_PER_DAY=1)
class ReportLimitApiTests(ApiTestBase):
    def test_limit_reached_returns_429(self):
        finished_report(self.user)
        response = self.api.post(reverse("api_report_list"), {"games": [self.game.pk]}, format="json")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Report limit reached (1 in 24 hours)", response.json()["detail"])
        self.assertEqual(WeaknessReport.objects.count(), 1)