from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile

User = get_user_model()

SIGNUP_DATA = {
    "username": "newplayer",
    "password1": "Kn1ght-Fork-42",
    "password2": "Kn1ght-Fork-42",
    "rating": "1350",
    "lichess_username": "newplayer_li",
}


class SignUpTests(TestCase):
    def test_signup_creates_user_and_profile_and_logs_in(self):
        response = self.client.post(reverse("signup"), SIGNUP_DATA)
        self.assertRedirects(response, reverse("game_list"))
        user = User.objects.get(username="newplayer")
        self.assertEqual(user.profile.rating, 1350)
        self.assertEqual(user.profile.lichess_username, "newplayer_li")
        # The session now belongs to the new user.
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_password_is_not_stored_as_plain_text(self):
        self.client.post(reverse("signup"), SIGNUP_DATA)
        user = User.objects.get(username="newplayer")
        self.assertNotEqual(user.password, SIGNUP_DATA["password1"])
        self.assertTrue(user.check_password(SIGNUP_DATA["password1"]))

    def test_mismatched_passwords_create_nothing(self):
        data = {**SIGNUP_DATA, "password2": "something-else-99"}
        response = self.client.post(reverse("signup"), data)
        self.assertEqual(response.status_code, 200)  # form shown again with errors
        self.assertFalse(User.objects.filter(username="newplayer").exists())
        self.assertEqual(UserProfile.objects.count(), 0)

    def test_impossible_rating_is_rejected(self):
        data = {**SIGNUP_DATA, "rating": "99999"}
        self.client.post(reverse("signup"), data)
        self.assertFalse(User.objects.filter(username="newplayer").exists())

    def test_rating_is_optional(self):
        data = {**SIGNUP_DATA, "rating": "", "lichess_username": ""}
        self.client.post(reverse("signup"), data)
        self.assertIsNone(User.objects.get(username="newplayer").profile.rating)


class LoginLogoutTests(TestCase):
    def setUp(self):
        User.objects.create_user("tester", password="pass12345")

    def test_login_redirects_to_game_list(self):
        response = self.client.post(
            reverse("login"), {"username": "tester", "password": "pass12345"}
        )
        self.assertRedirects(response, reverse("game_list"))

    def test_wrong_password_stays_on_login_page(self):
        response = self.client.post(
            reverse("login"), {"username": "tester", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_ends_session(self):
        self.client.login(username="tester", password="pass12345")
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)