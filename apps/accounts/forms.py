from django import forms
from django.contrib.auth.forms import UserCreationForm


class SignUpForm(UserCreationForm):
    # Extra profile fields; UserCreationForm already handles username and passwords.
    rating = forms.IntegerField(required=False, min_value=100, max_value=3500)
    lichess_username = forms.CharField(required=False, max_length=30)