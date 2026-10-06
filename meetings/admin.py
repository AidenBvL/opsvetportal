from django.contrib import admin

from .models import MeetingBlock, MeetingItem

admin.site.register([MeetingBlock, MeetingItem])
