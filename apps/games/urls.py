from django.urls import path
from .views.game_views import game_list, upload_game

urlpatterns = [
    path("upload/", upload_game, name="upload_game"),
    path("", game_list, name="game_list"),
]