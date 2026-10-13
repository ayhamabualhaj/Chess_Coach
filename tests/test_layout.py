from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tests.test_pgn_import import VALID_PGN


class BaseLayoutTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("tester", password="pass12345")

    def test_pages_use_base_layout(self):
        response = self.client.get(reverse("login"))
        self.assertTemplateUsed(response, "base.html")

    def test_anonymous_nav_shows_login_and_signup(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, reverse("signup"))
        self.assertNotContains(response, "Log out")

    def test_logged_in_nav_shows_username_and_logout(self):
        self.client.login(username="tester", password="pass12345")
        response = self.client.get(reverse("game_list"))
        self.assertContains(response, "tester")
        self.assertContains(response, "Log out")

    def test_upload_shows_success_message(self):
        self.client.login(username="tester", password="pass12345")
        response = self.client.post(reverse("upload_game"), {"pgn": VALID_PGN}, follow=True)
        self.assertContains(response, "Uploaded 1 game.")