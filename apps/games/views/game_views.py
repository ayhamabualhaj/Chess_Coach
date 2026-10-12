from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.games.services import game_service
from apps.games.services.analysis_service import AnalysisError, analyse_game
from apps.games.services.pgn_import_service import InvalidPGNError, import_pgn


@login_required
def upload_game(request):
    if request.method == "POST":
        pgn = request.POST.get("pgn", "")
        try:
            import_pgn(request.user, pgn)
        except InvalidPGNError as e:
            return render(request, "games/upload.html", {"error": str(e), "pgn": pgn})
        messages.success(request, "Game uploaded successfully.")
        return redirect("game_list")
    return render(request, "games/upload.html")


@login_required
def game_list(request):
    games = game_service.list_games(request.user)
    return render(request, "games/list.html", {"games": games})


@login_required
def game_detail(request, game_id):
    detail = game_service.get_game_detail(request.user, game_id)
    if detail is None:
        raise Http404("Game not found")
    return render(request, "games/detail.html", detail)


@login_required
@require_POST
def analyse(request, game_id):
    game = game_service.get_game(request.user, game_id)
    if game is None:
        raise Http404("Game not found")
    try:
        summary = analyse_game(game.pk)
    except AnalysisError as e:
        messages.error(request, str(e))
    else:
        messages.success(
            request, f"Analysed {summary['moves']} moves and found {summary['mistakes']} mistakes."
        )
    return redirect("game_detail", game_id=game.pk)
