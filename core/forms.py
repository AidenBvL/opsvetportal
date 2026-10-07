from django import forms
from django.contrib.auth.models import Group, Permission, User
from django.contrib.auth.password_validation import validate_password

from .models import Terminal

PORTAL_APPS = ["core", "planning", "meetings", "actions", "shipments", "documents", "auth"]
ACTION_LABELS = {"view": "bekijken", "add": "toevoegen", "change": "wijzigen", "delete": "verwijderen"}


def portal_permissions():
    return (
        Permission.objects.filter(content_type__app_label__in=PORTAL_APPS)
        .exclude(content_type__model__in=["permission"])
        .select_related("content_type")
        .order_by("content_type__app_label", "content_type__model", "codename")
    )


def grouped_permissions(field):
    """Groepeer checkboxes per model voor een overzichtelijke rechtenmatrix."""
    selected = {str(v) for v in (field.value() or [])}
    rows = {}
    for perm in field.field.queryset:
        model = perm.content_type.model_class()
        label = model._meta.verbose_name_plural.capitalize() if model else perm.content_type.model
        row = rows.setdefault(perm.content_type_id, {"label": label, "standard": {}, "extra": []})
        action = perm.codename.split("_", 1)[0]
        item = {"id": perm.id, "checked": str(perm.id) in selected, "name": perm.name}
        if action in ACTION_LABELS and perm.codename.endswith(perm.content_type.model):
            row["standard"][action] = item
        else:
            row["extra"].append(item)
    return list(rows.values())


class PermissionsField(forms.ModelMultipleChoiceField):
    def __init__(self, **kwargs):
        super().__init__(queryset=portal_permissions(), required=False, widget=forms.CheckboxSelectMultiple, **kwargs)


class UserForm(forms.ModelForm):
    password1 = forms.CharField(label="Wachtwoord", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Herhaal wachtwoord", widget=forms.PasswordInput, required=False)
    groups = forms.ModelMultipleChoiceField(
        label="Rollen", queryset=Group.objects.all(), required=False, widget=forms.CheckboxSelectMultiple
    )
    user_permissions = PermissionsField(label="Extra rechten (bovenop de rollen)")
    employee = forms.ModelChoiceField(label="Gekoppelde medewerker", queryset=None, required=False)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_superuser", "groups", "user_permissions"]
        labels = {"is_superuser": "Beheerder (alle rechten)", "is_active": "Actief"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from planning.models import Employee

        self.fields["employee"].queryset = Employee.objects.filter(active=True)
        if self.instance.pk:
            self.fields["employee"].initial = getattr(self.instance, "employee", None)
            self.fields["password1"].help_text = "Leeg laten om het wachtwoord niet te wijzigen."
        else:
            self.fields["password1"].required = True
            self.fields["password2"].required = True

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "De wachtwoorden komen niet overeen.")
            else:
                try:
                    validate_password(p1, self.instance)
                except forms.ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        user.is_staff = user.is_superuser
        if commit:
            user.save()
            self.save_m2m()
            from planning.models import Employee

            Employee.objects.filter(user=user).exclude(pk=getattr(self.cleaned_data.get("employee"), "pk", None)).update(user=None)
            employee = self.cleaned_data.get("employee")
            if employee:
                employee.user = user
                employee.save(update_fields=["user"])
        return user

    def permission_rows(self):
        return grouped_permissions(self["user_permissions"])


class GroupForm(forms.ModelForm):
    permissions = PermissionsField(label="Rechten")

    class Meta:
        model = Group
        fields = ["name", "permissions"]
        labels = {"name": "Naam rol"}

    def permission_rows(self):
        return grouped_permissions(self["permissions"])


class NotificationPreferenceForm(forms.ModelForm):
    class Meta:
        from .models import NotificationPreference

        model = NotificationPreference
        exclude = ["user"]


class CustomerAccountForm(forms.Form):
    first_name = forms.CharField(label="Voornaam", max_length=150)
    last_name = forms.CharField(label="Achternaam", max_length=150, required=False)
    email = forms.EmailField(label="E-mailadres (wordt de gebruikersnaam)")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Er bestaat al een account met dit e-mailadres.")
        return email


class TerminalForm(forms.ModelForm):
    class Meta:
        model = Terminal
        fields = ["name", "code", "port", "company", "address", "website", "aliases", "active"]

    def __init__(self, *args, **kwargs):
        from django.db.models import Q

        super().__init__(*args, **kwargs)
        # Alleen containerhavens in de keuzelijst (er zijn er 17.000+), plus de huidige haven.
        current = Q(pk=self.instance.port_id) if self.instance.port_id else Q(pk__in=[])
        self.fields["port"].queryset = self.fields["port"].queryset.filter(Q(container_port=True) | current)
