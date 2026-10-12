from django.urls import path

from .views.game_views import analyse, game_detail, game_list, upload_game

urlpatterns = [
    path("upload/", upload_game, name="upload_game"),
    path("<int:game_id>/", game_detail, name="game_detail"),
    path("<int:game_id>/analyse/", analyse, name="analyse_game"),
    path("", game_list, name="game_list"),
]
