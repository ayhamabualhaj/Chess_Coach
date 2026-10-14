from django.urls import path

from .views.game_api_views import AnalyseGameAPI, GameDetailAPI, GameListAPI

urlpatterns = [
    path("games/", GameListAPI.as_view(), name="api_game_list"),
    path("games/<int:game_id>/", GameDetailAPI.as_view(), name="api_game_detail"),
    path("games/<int:game_id>/analyse/", AnalyseGameAPI.as_view(), name="api_analyse_game"),
]