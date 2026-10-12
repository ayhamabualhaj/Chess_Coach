from django.contrib import admin
from .models import Game, Mistake, Move

admin.site.register(Game)
admin.site.register(Move)
admin.site.register(Mistake)