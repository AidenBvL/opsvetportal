from django import forms

from planning.models import Employee

from .models import MeetingBlock, MeetingItem


class MeetingItemForm(forms.ModelForm):
    class Meta:
        model = MeetingItem
        fields = ["title", "details", "raised_by", "colleagues", "customer", "sea_shipment", "road_transport", "status", "answer"]
        widgets = {
            "details": forms.Textarea(attrs={"rows": 2}),
            "answer": forms.Textarea(attrs={"rows": 2}),
            "colleagues": forms.SelectMultiple(attrs={"size": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active = Employee.objects.filter(active=True)
        self.fields["raised_by"].queryset = active
        self.fields["colleagues"].queryset = active
        from shipments.models import RoadTransport, SeaShipment

        self.fields["sea_shipment"].queryset = SeaShipment.objects.select_related("customer").order_by("-created_at")
        self.fields["road_transport"].queryset = RoadTransport.objects.select_related("customer").order_by("-created_at")


class QuickItemForm(forms.ModelForm):
    """Compact formulier om snel een vraag aan een overlegblok toe te voegen."""

    class Meta:
        model = MeetingItem
        fields = ["title", "raised_by", "colleagues", "customer"]
        widgets = {"colleagues": forms.SelectMultiple(attrs={"size": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active = Employee.objects.filter(active=True)
        self.fields["raised_by"].queryset = active
        self.fields["colleagues"].queryset = active


class MeetingBlockForm(forms.ModelForm):
    class Meta:
        model = MeetingBlock
        fields = ["attendees", "notes"]
        widgets = {"attendees": forms.CheckboxSelectMultiple, "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attendees"].queryset = Employee.objects.filter(active=True)
