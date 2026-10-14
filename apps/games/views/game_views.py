from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.games.services import game_service
from apps.games.services.pgn_import_service import MAX_ERRORS_SHOWN, MAX_PGN_BYTES, InvalidPGNError, import_pgn

ANALYSIS_MESSAGES = {
    game_service.QUEUED: (messages.INFO, "Analysis started. This page will update when it is finished."),
    game_service.ALREADY_QUEUED: (messages.WARNING, "This game is already being analysed."),
}


def _read_upload(request) -> str:
    """The PGN from the chosen file, or else from the text box."""
    upload = request.FILES.get("pgn_file")
    if upload is None:
        return request.POST.get("pgn", "")
    if upload.size > MAX_PGN_BYTES:
        raise InvalidPGNError("This file is too large (more than 5 MB). Please split it into smaller files.")
    return upload.read().decode("utf-8", errors="replace")


@login_required
def upload_game(request):
    if request.method == "POST":
        pgn = request.POST.get("pgn", "")
        played_as = request.POST.get("played_as", "auto")
        try:
            result = import_pgn(request.user, _read_upload(request), played_as)
        except InvalidPGNError as e:
            return render(
                request, "games/upload.html", {"error": str(e), "pgn": pgn, "played_as": played_as}
            )
        imported = len(result.games)
        if imported:
            messages.success(request, f"Uploaded {imported} game{'s' if imported != 1 else ''}.")
        if result.duplicates:
            messages.info(
                request, f"Skipped {result.duplicates} game{'s' if result.duplicates != 1 else ''} you had already uploaded."
            )
        for error in result.errors[:MAX_ERRORS_SHOWN]:
            messages.warning(request, f"Skipped {error}")
        if len(result.errors) > MAX_ERRORS_SHOWN:
            messages.warning(request, f"…and {len(result.errors) - MAX_ERRORS_SHOWN} more games with errors.")
        return redirect("game_list")
    return render(request, "games/upload.html")


@login_required
def game_list(request):
    context = game_service.list_games(request.user, request.GET.get("show", "all"), request.GET.get("page", 1))
    return render(request, "games/list.html", context)


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
    outcome = game_service.request_analysis(game)
    if outcome == game_service.QUEUE_FULL:
        messages.warning(
            request,
            f"You already have {settings.MAX_ANALYSIS_QUEUE} games waiting for analysis. "
            "Please wait until some of them are finished.",
        )
    else:
        level, text = ANALYSIS_MESSAGES[outcome]
        messages.add_message(request, level, text)
    return redirect("game_detail", game_id=game.pk)


@login_required
@require_POST
def analyse_all(request):
    result = game_service.analyse_all(request.user)
    if result["queued"]:
        text = f"{result['queued']} game{'s' if result['queued'] != 1 else ''} queued for analysis."
        if result["waiting"]:
            text += f" {result['waiting']} more will be possible once these are finished."
        messages.info(request, text)
    elif result["waiting"]:
        messages.warning(request, "The analysis queue is full. Please wait until some games are finished.")
    else:
        messages.info(request, "All your games are already analysed or waiting.")
    return redirect("game_list")


@login_required
@require_POST
def set_color(request, game_id):
    game = game_service.get_game(request.user, game_id)
    if game is None:
        raise Http404("Game not found")
    if game_service.set_user_color(game, request.POST.get("color", "")):
        messages.success(request, "Saved which side you played.")
    else:
        messages.error(request, "Please choose White or Black.")
    return redirect("game_detail", game_id=game.pk)


@login_required
@require_POST
def delete_game(request, game_id):
    game = game_service.get_game(request.user, game_id)
    if game is None:
        raise Http404("Game not found")
    game_service.delete_game(game)
    messages.success(request, "Game deleted.")
    return redirect("game_list")


@login_required
@require_POST
def delete_games(request):
    deleted = game_service.delete_games(request.user, request.POST.getlist("games"))
    if deleted:
        messages.success(request, f"Deleted {deleted} game{'s' if deleted != 1 else ''}.")
    else:
        messages.warning(request, "Tick at least one game to delete.")
    return redirect(reverse("game_list") + "?" + request.POST.get("back", ""))