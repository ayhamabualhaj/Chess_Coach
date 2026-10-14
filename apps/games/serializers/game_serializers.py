"""Serializers turn games and moves into JSON for the API (Django REST Framework).

https://www.django-rest-framework.org/api-guide/serializers/
"""
from rest_framework import serializers

from apps.games.models import Game, Move


class GameStatusSerializer(serializers.ModelSerializer):
    """The analysis status of one game; the game page asks for it while it waits."""

    label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Game
        fields = ["status", "label"]


class QueueStatusSerializer(serializers.Serializer):
    """How many of the user's games are waiting for or in analysis."""

    in_progress = serializers.IntegerField(min_value=0)


class GameSerializer(serializers.ModelSerializer):
    """A game in a list: players, result and analysis status, without the moves."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    user_outcome = serializers.CharField(read_only=True)  # "win" / "loss" / "draw" / ""

    class Meta:
        model = Game
        fields = [
            "id", "white", "black", "result", "played_on", "opening", "user_color",
            "user_outcome", "status", "status_label", "created_at",
        ]
        read_only_fields = fields


class MoveSerializer(serializers.ModelSerializer):
    """One analysed move with its engine evaluation and labels."""

    # From the move's Mistake row; null for moves that were not a mistake.
    severity = serializers.CharField(source="mistake.severity", read_only=True, allow_null=True, default=None)
    motif = serializers.CharField(source="mistake.motif", read_only=True, allow_null=True, default=None)

    class Meta:
        model = Move
        fields = [
            "ply", "color", "san", "uci", "eval_before", "eval_after", "best_move_uci",
            "cp_loss", "label", "severity", "motif",
        ]
        read_only_fields = fields


class GameDetailSerializer(GameSerializer):
    """A game with all its moves and the accuracy of both players.

    The moves and accuracy are computed by game_service and passed in the context,
    so the serializer only formats them.
    """

    accuracy = serializers.SerializerMethodField()
    moves = serializers.SerializerMethodField()

    class Meta(GameSerializer.Meta):
        fields = [*GameSerializer.Meta.fields, "accuracy", "moves"]
        read_only_fields = fields

    def get_accuracy(self, game) -> dict:
        return self.context["accuracy"]

    def get_moves(self, game) -> list:
        return MoveSerializer(self.context["moves"], many=True).data