from django.urls import path

from .views.game_views import (
    analyse, analyse_all, delete_game, delete_games, game_detail, game_list, game_status,
    queue_status, set_color, upload_game,
)

urlpatterns = [
    path("upload/", upload_game, name="upload_game"),
    path("analyse-all/", analyse_all, name="analyse_all"),
    path("delete/", delete_games, name="delete_games"),
    path("queue/", queue_status, name="queue_status"),
    path("<int:game_id>/", game_detail, name="game_detail"),
    path("<int:game_id>/analyse/", analyse, name="analyse_game"),
    path("<int:game_id>/status/", game_status, name="game_status"),
    path("<int:game_id>/side/", set_color, name="set_game_color"),
    path("<int:game_id>/delete/", delete_game, name="delete_game"),
    path("", game_list, name="game_list"),
]
