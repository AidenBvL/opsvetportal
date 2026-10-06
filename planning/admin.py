from django.contrib import admin

from .models import Absence, Department, Employee, Holiday, RosterMonth, Shift, WorkFromHomeDay


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["date", "shift_type", "employee", "linked_to_wfh", "is_manual"]
    list_filter = ["shift_type", "employee"]
    date_hierarchy = "date"


admin.site.register([Absence, Department, Employee, Holiday, RosterMonth, WorkFromHomeDay])
