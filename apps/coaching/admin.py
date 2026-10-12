from django.contrib import admin
from .models import TrainingPlan, WeaknessReport

admin.site.register(WeaknessReport)
admin.site.register(TrainingPlan)