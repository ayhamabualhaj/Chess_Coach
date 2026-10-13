from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.games.models import Game, Move
from apps.games.services.game_service import GAMES_PER_PAGE
from tests.test_game_pages import AFTER_E4_FEN, DUMMY_TASKS, START_FEN

User = get_user_model()
PGN = "1. e4 e5 *"


class GameListTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pass12345")
        self.client.login(username="tester", password="pass12345")

    def make_games(self, count, **fields):
        return Game.objects.bulk_create(Game(user=self.user, pgn=PGN, **fields) for _ in range(count))


class PaginationAndFilterTests(GameListTestBase):
    def test_fifty_games_per_page(self):
        self.make_games(GAMES_PER_PAGE + 1)
        first = self.client.get(reverse("game_list"))
        second = self.client.get(reverse("game_list"), {"page": 2})
        self.assertEqual(len(first.context["page"].object_list), 50)
        self.assertEqual(len(second.context["page"].object_list), 1)
        self.assertContains(first, "Page 1 of 2")

    def test_filters_and_counts(self):
        self.make_games(2, status=Game.Status.DONE, user_color="white")
        self.make_games(3)  # not analysed, side unknown
        response = self.client.get(reverse("game_list"), {"show": "todo"})
        self.assertEqual(len(response.context["page"].object_list), 3)
        self.assertEqual(response.context["counts"], {"all": 5, "todo": 3, "done": 2, "side": 3})

    def test_unknown_filter_shows_all(self):
        self.make_games(2)
        response = self.client.get(reverse("game_list"), {"show": "nonsense"})
        self.assertEqual(response.context["show"], "all")

    def test_result_is_shown_from_the_users_side(self):
        Game.objects.create(user=self.user, pgn=PGN, white="tester", black="x", result="1-0", user_color="white")
        Game.objects.create(user=self.user, pgn=PGN, white="tester", black="y", result="0-1", user_color="white")
        response = self.client.get(reverse("game_list"))
        self.assertContains(response, "You won")
        self.assertContains(response, "You lost")


@override_settings(TASKS=DUMMY_TASKS, MAX_ANALYSIS_QUEUE=3)
class AnalyseAllTests(GameListTestBase):
    def test_queues_only_as_many_as_the_limit(self):
        self.make_games(5)
        response = self.client.post(reverse("analyse_all"), follow=True)
        self.assertEqual(Game.objects.filter(status=Game.Status.QUEUED).count(), 3)
        self.assertContains(response, "3 games queued for analysis. 2 more will be possible")

    def test_full_queue_blocks_more(self):
        self.make_games(3, status=Game.Status.QUEUED)
        waiting = self.make_games(1)[0]
        response = self.client.post(reverse("analyse_all"), follow=True)
        self.assertContains(response, "queue is full")
        response = self.client.post(reverse("analyse_game", args=[waiting.pk]), follow=True)
        self.assertContains(response, "You already have 3 games waiting")
        waiting.refresh_from_db()
        self.assertEqual(waiting.status, Game.Status.PENDING)

    def test_analysed_games_are_not_queued_again(self):
        self.make_games(2, status=Game.Status.DONE)
        response = self.client.post(reverse("analyse_all"), follow=True)
        self.assertContains(response, "already analysed or waiting")
        self.assertEqual(Game.objects.filter(status=Game.Status.QUEUED).count(), 0)

    def test_queue_status_endpoint(self):
        self.make_games(2, status=Game.Status.QUEUED)
        self.assertEqual(self.client.get(reverse("queue_status")).json(), {"in_progress": 2})

    def test_list_refreshes_while_games_are_analysed(self):
        self.make_games(1, status=Game.Status.RUNNING)
        self.assertContains(self.client.get(reverse("game_list")), 'id="queue-progress"')


class DeleteSelectedTests(GameListTestBase):
    def test_deletes_only_the_users_ticked_games(self):
        mine = self.make_games(3)
        other_user = User.objects.create_user("other", password="pass12345")
        theirs = Game.objects.create(user=other_user, pgn=PGN)
        ids = [mine[0].pk, mine[1].pk, theirs.pk]
        response = self.client.post(reverse("delete_games"), {"games": ids, "back": "show=all"}, follow=True)
        self.assertContains(response, "Deleted 2 games.")
        self.assertEqual(Game.objects.filter(user=self.user).count(), 1)
        self.assertTrue(Game.objects.filter(pk=theirs.pk).exists())

    def test_nothing_ticked(self):
        response = self.client.post(reverse("delete_games"), {}, follow=True)
        self.assertContains(response, "Tick at least one game")


class GamePageMoveTypeTests(GameListTestBase):
    def setUp(self):
        super().setUp()
        self.game = Game.objects.create(user=self.user, pgn=PGN, white="tester", black="x", user_color="white")

    def add_move(self, ply, color, san, fen, eval_after, label):
        Move.objects.create(
            game=self.game, ply=ply, color=color, san=san, uci="e2e4", fen_before=fen,
            eval_before=20, eval_after=eval_after, best_move_uci="e2e4", cp_loss=0, label=label,
        )

    def test_types_counts_and_accuracy_are_shown(self):
        self.add_move(1, "white", "e4", START_FEN, 20, "best")
        self.add_move(2, "black", "e5", AFTER_E4_FEN, 20, "great")
        response = self.client.get(reverse("game_detail", args=[self.game.pk]))
        self.assertContains(response, 'class="move-label label-great"')
        self.assertContains(response, "100.0%")
        self.assertContains(response, "What do the move types mean?")
        white = response.context["stats"]["white"]["labels"]
        self.assertEqual(next(item["count"] for item in white if item["label"] == "best"), 1)

    def test_old_analysis_asks_to_analyse_again(self):
        self.add_move(1, "white", "e4", START_FEN, 20, "")
        response = self.client.get(reverse("game_detail", args=[self.game.pk]))
        self.assertContains(response, "analysed before move types")
