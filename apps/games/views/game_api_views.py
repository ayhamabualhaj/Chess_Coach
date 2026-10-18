"""JSON API for games (Django REST Framework).

Every view only reads the request, calls game_service and returns serialized data;
authentication (session or token) and "must be logged in" come from the
REST_FRAMEWORK settings.
"""
from django.http import Http404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.games.serializers import GameDetailSerializer, GameSerializer, GameStatusSerializer, QueueStatusSerializer
from apps.games.services import game_service

# HTTP status for each answer of game_service.request_analysis.
ANALYSIS_STATUS = {
    game_service.QUEUED: status.HTTP_202_ACCEPTED,  # accepted, runs in the background
    game_service.ALREADY_QUEUED: status.HTTP_409_CONFLICT,
    game_service.QUEUE_FULL: status.HTTP_429_TOO_MANY_REQUESTS,
}


def _own_game(request, game_id):
    game = game_service.get_game(request.user, game_id)
    if game is None:
        raise Http404("Game not found")
    return game


class GameListAPI(generics.ListAPIView):
    """GET /api/games/?show=all|todo|done|side  – the user's games, 50 per page."""

    serializer_class = GameSerializer

    def get_queryset(self):
        return game_service.filter_games(self.request.user, self.request.query_params.get("show", "all"))


class GameDetailAPI(APIView):
    """GET /api/games/<id>/  – one game with every move, its labels and the accuracy."""

    def get(self, request, game_id):
        analysis = game_service.get_game_analysis(request.user, game_id)
        if analysis is None:
            raise Http404("Game not found")
        context = {"moves": analysis["moves"], "accuracy": analysis["accuracy"]}
        return Response(GameDetailSerializer(analysis["game"], context=context).data)


class AnalyseGameAPI(APIView):
    """POST /api/games/<id>/analyse/  – put the game in the analysis queue."""

    def post(self, request, game_id):
        game = _own_game(request, game_id)
        outcome = game_service.request_analysis(game)
        return Response({"result": outcome, **GameStatusSerializer(game).data}, status=ANALYSIS_STATUS[outcome])


class GameStatusAPI(APIView):
    """GET /games/<id>/status/  – the game page asks this every 2 s while an analysis runs."""

    def get(self, request, game_id):
        game = game_service.get_game_status(request.user, game_id)
        if game is None:
            raise Http404("Game not found")
        return Response(GameStatusSerializer(game).data)


class QueueStatusAPI(APIView):
    """GET /games/queue/  – the games list asks this every 3 s while games are analysed."""

    def get(self, request):
        data = {"in_progress": game_service.count_in_progress(request.user)}
        return Response(QueueStatusSerializer(data).data)