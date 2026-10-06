from django.contrib import admin

from .models import Action, ExtraCost

admin.site.register([Action, ExtraCost])
