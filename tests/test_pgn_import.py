from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.games.models import Game
from apps.games.services.pgn_import_service import InvalidPGNError, import_pgn

VALID_PGN = """[Event "Test"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0
"""


class ImportPgnServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="pass12345")

    def test_valid_pgn_is_saved_for_user(self):
        game = import_pgn(self.user, VALID_PGN)
        self.assertEqual(Game.objects.count(), 1)
        self.assertEqual(game.user, self.user)

    def test_empty_input_is_rejected(self):
        with self.assertRaises(InvalidPGNError):
            import_pgn(self.user, "   ")
        self.assertEqual(Game.objects.count(), 0)

    def test_text_without_moves_is_rejected(self):
        with self.assertRaises(InvalidPGNError):
            import_pgn(self.user, "hello world")

    def test_illegal_move_is_rejected(self):
        # Ke3 is illegal: the king cannot move two squares.
        with self.assertRaises(InvalidPGNError):
            import_pgn(self.user, "1. e4 e5 2. Ke3 Ke7")
        self.assertEqual(Game.objects.count(), 0)


class UploadViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="pass12345")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("upload_game"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_logged_in_upload_redirects_to_list(self):
        self.client.login(username="tester", password="pass12345")
        response = self.client.post(reverse("upload_game"), {"pgn": VALID_PGN})
        self.assertRedirects(response, reverse("game_list"))
        self.assertEqual(Game.objects.filter(user=self.user).count(), 1)

    def test_users_only_see_their_own_games(self):
        other = get_user_model().objects.create_user("other", password="pass12345")
        import_pgn(other, VALID_PGN)
        self.client.login(username="tester", password="pass12345")
        response = self.client.get(reverse("game_list"))
        self.assertEqual(len(response.context["games"]), 0)