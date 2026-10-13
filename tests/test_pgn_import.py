from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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

# Three games in one file, like a Lichess export: the tester plays White, then Black,
# and the third game has an illegal move.
THREE_GAMES = """[Site "https://lichess.org/aaaa1111"]
[Date "2025.03.14"]
[White "tester"]
[Black "rival"]
[Result "1-0"]
[Opening "Italian Game"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 1-0

[Site "https://lichess.org/bbbb2222"]
[Date "2025.03.13"]
[White "rival"]
[Black "tester"]
[Result "1-0"]

1. d4 d5 2. c4 e6 1-0

[White "rival"]
[Black "tester"]
[Result "*"]

1. e4 e5 2. Ke3 *
"""


class ImportPgnServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="pass12345")

    def test_valid_pgn_is_saved_for_user(self):
        result = import_pgn(self.user, VALID_PGN)
        self.assertEqual(Game.objects.count(), 1)
        self.assertEqual(result.games[0].user, self.user)

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


class MultipleGamesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="pass12345")

    def test_every_game_is_saved_separately(self):
        result = import_pgn(self.user, THREE_GAMES)
        first, second = result.games
        self.assertEqual(len(result.games), 2)
        self.assertNotIn("bbbb2222", first.pgn)  # each game keeps only its own PGN
        self.assertIn("1. d4 d5", second.pgn)

    def test_side_is_detected_per_game(self):
        first, second = import_pgn(self.user, THREE_GAMES).games
        self.assertEqual((first.user_color, second.user_color), ("white", "black"))

    def test_broken_game_is_skipped_and_reported(self):
        result = import_pgn(self.user, THREE_GAMES)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("Game 3", result.errors[0])

    def test_date_and_opening_are_saved(self):
        first = import_pgn(self.user, THREE_GAMES).games[0]
        self.assertEqual((first.played_on, first.opening), (date(2025, 3, 14), "Italian Game"))

    def test_first_game_of_the_file_is_listed_first(self):
        import_pgn(self.user, THREE_GAMES)
        self.assertEqual(Game.objects.filter(user=self.user).first().played_on, date(2025, 3, 14))

    def test_same_games_are_not_uploaded_twice(self):
        import_pgn(self.user, THREE_GAMES)
        result = import_pgn(self.user, THREE_GAMES)
        self.assertEqual((len(result.games), result.duplicates), (0, 2))
        self.assertEqual(Game.objects.count(), 2)

    def test_other_users_can_upload_the_same_game(self):
        import_pgn(self.user, VALID_PGN)
        other = get_user_model().objects.create_user("other", password="pass12345")
        self.assertEqual(len(import_pgn(other, VALID_PGN).games), 1)


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
        self.assertEqual(len(response.context["page"].object_list), 0)

    def test_pgn_file_upload_with_report(self):
        self.client.login(username="tester", password="pass12345")
        upload = SimpleUploadedFile("games.pgn", THREE_GAMES.encode(), content_type="application/x-chess-pgn")
        response = self.client.post(reverse("upload_game"), {"pgn_file": upload, "played_as": "auto"}, follow=True)
        self.assertEqual(Game.objects.filter(user=self.user).count(), 2)
        self.assertContains(response, "Uploaded 2 games.")
        self.assertContains(response, "Skipped Game 3")

    def test_duplicates_are_reported(self):
        self.client.login(username="tester", password="pass12345")
        self.client.post(reverse("upload_game"), {"pgn": VALID_PGN})
        response = self.client.post(reverse("upload_game"), {"pgn": VALID_PGN}, follow=True)
        self.assertContains(response, "Skipped 1 game you had already uploaded.")

    def test_too_large_file_is_rejected(self):
        self.client.login(username="tester", password="pass12345")
        upload = SimpleUploadedFile("huge.pgn", b" " * (5 * 1024 * 1024 + 1))
        response = self.client.post(reverse("upload_game"), {"pgn_file": upload})
        self.assertContains(response, "too large")
        self.assertEqual(Game.objects.count(), 0)
