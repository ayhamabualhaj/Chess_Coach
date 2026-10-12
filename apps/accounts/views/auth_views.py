from django.contrib.auth import login
from django.shortcuts import redirect, render

from apps.accounts.forms import SignUpForm
from apps.accounts.services import account_service


def signup(request):
    if request.user.is_authenticated:
        return redirect("game_list")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = account_service.register_user(
                username=data["username"],
                password=data["password1"],
                rating=data["rating"],
                lichess_username=data["lichess_username"],
            )
            login(request, user)
            return redirect("game_list")
    else:
        form = SignUpForm()

    return render(request, "accounts/signup.html", {"form": form})