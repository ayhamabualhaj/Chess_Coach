from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.games.repositories import game_repository
from apps.games.services.pgn_import_service import InvalidPGNError, import_pgn


@login_required
def upload_game(request):
    if request.method == "POST":
        pgn = request.POST.get("pgn", "")
        try:
            import_pgn(request.user, pgn)
        except InvalidPGNError as e:
            return render(request, "games/upload.html", {"error": str(e), "pgn": pgn})
        return redirect("game_list")
    return render(request, "games/upload.html")


@login_required
def game_list(request):
    games = game_repository.list_games_for_user(request.user)
    return render(request, "games/list.html", {"games": games})