"""Kleine generieke CRUD-laag zodat stamgegevens geen eigen templates per model nodig hebben."""

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import ProtectedError, Q
from django.shortcuts import redirect
from django.urls import path, reverse
from django.views import generic


def perm(model, action):
    return f"{model._meta.app_label}.{action}_{model._meta.model_name}"


class CrudMixin(PermissionRequiredMixin):
    model = None
    namespace = ""
    list_display = ()
    search_fields = ()
    list_filters = ()  # veldnamen met choices/FK voor filterdropdowns
    detail_url_name = None

    @property
    def base_name(self):
        return self.model._meta.model_name

    def url_name(self, action):
        prefix = f"{self.namespace}:" if self.namespace else ""
        return f"{prefix}{self.base_name}_{action}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        opts = self.model._meta
        user = self.request.user
        context.update(
            {
                "opts": opts,
                "verbose_name": opts.verbose_name,
                "verbose_name_plural": opts.verbose_name_plural,
                "list_url": reverse(self.url_name("list")),
                "create_url": reverse(self.url_name("create")) if user.has_perm(perm(self.model, "add")) else None,
                "can_change": user.has_perm(perm(self.model, "change")),
                "can_delete": user.has_perm(perm(self.model, "delete")),
                "update_url_name": self.url_name("update"),
                "delete_url_name": self.url_name("delete"),
                "detail_url_name": self.detail_url_name,
            }
        )
        return context


class CrudListView(CrudMixin, generic.ListView):
    template_name = "core/generic_list.html"
    paginate_by = 50

    def get_permission_required(self):
        return [perm(self.model, "view")]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q and self.search_fields:
            cond = Q()
            for field in self.search_fields:
                cond |= Q(**{f"{field}__icontains": q})
            qs = qs.filter(cond)
        for field in self.list_filters:
            value = self.request.GET.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        columns = []
        for item in self.list_display:
            name, label = item if isinstance(item, tuple) else (item, None)
            if label is None:
                try:
                    label = self.model._meta.get_field(name).verbose_name
                except Exception:  # noqa: BLE001 - property zonder modelveld
                    label = name.replace("_", " ")
            columns.append({"name": name, "label": label})
        filters = []
        for field_name in self.list_filters:
            field = self.model._meta.get_field(field_name)
            if field.choices:
                options = [(str(k), v) for k, v in field.choices if k != ""]
            elif field.is_relation:
                options = [(str(o.pk), str(o)) for o in field.related_model.objects.all()]
            elif field.get_internal_type() == "BooleanField":
                options = [("True", "Ja"), ("False", "Nee")]
            else:
                continue
            filters.append({"name": field_name, "label": field.verbose_name, "options": options,
                            "value": self.request.GET.get(field_name, "")})
        context.update({"columns": columns, "q": self.request.GET.get("q", ""), "filters": filters,
                        "searchable": bool(self.search_fields)})
        return context


class CrudFormMixin(CrudMixin):
    template_name = "core/generic_form.html"
    fields = None
    form_class = None

    def get_success_url(self):
        if self.detail_url_name:
            return reverse(self.detail_url_name, args=[self.object.pk])
        return reverse(self.url_name("list"))

    def form_valid(self, form):
        if hasattr(form.instance, "created_by_id") and not form.instance.pk:
            form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"{self.model._meta.verbose_name.capitalize()} '{self.object}' opgeslagen.")
        return response


class CrudCreateView(CrudFormMixin, generic.CreateView):
    def get_permission_required(self):
        return [perm(self.model, "add")]

    def get_initial(self):
        initial = super().get_initial()
        # Voorinvullen via querystring, bijv. ?customer=3
        for key, value in self.request.GET.items():
            initial[key] = value
        return initial


class CrudUpdateView(CrudFormMixin, generic.UpdateView):
    def get_permission_required(self):
        return [perm(self.model, "change")]


class CrudDeleteView(CrudMixin, generic.DeleteView):
    template_name = "core/generic_confirm_delete.html"

    def get_permission_required(self):
        return [perm(self.model, "delete")]

    def get_success_url(self):
        return reverse(self.url_name("list"))

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "Kan niet verwijderen: er zijn nog dossiers aan gekoppeld. Zet het item op inactief.")
            return redirect(self.url_name("list"))
        messages.success(self.request, "Verwijderd.")
        return response


def crud_urls(model, namespace, fields=None, form_class=None, list_display=(), search_fields=(), list_filters=(),
              list_view=None, create_view=None, update_view=None, detail_url_name=None, queryset=None, slug=None):
    """Maakt list/create/update/delete URL's voor een model."""
    name = model._meta.model_name
    slug = slug or name
    attrs = {"model": model, "namespace": namespace, "detail_url_name": detail_url_name}
    form_attrs = dict(attrs, fields=None if form_class else fields, form_class=form_class)
    list_attrs = dict(attrs)
    for key, value in (("list_display", list_display), ("search_fields", search_fields),
                       ("list_filters", list_filters), ("queryset", queryset)):
        if value:
            list_attrs[key] = value
    if list_view and not detail_url_name:
        list_attrs.pop("detail_url_name")
    list_cls = type(f"{name}List", (list_view or CrudListView,), list_attrs)
    create_cls = type(f"{name}Create", (create_view or CrudCreateView,), form_attrs)
    update_cls = type(f"{name}Update", (update_view or CrudUpdateView,), form_attrs)
    delete_cls = type(f"{name}Delete", (CrudDeleteView,), attrs)
    return [
        path(f"{slug}/", list_cls.as_view(), name=f"{name}_list"),
        path(f"{slug}/nieuw/", create_cls.as_view(), name=f"{name}_create"),
        path(f"{slug}/<int:pk>/bewerken/", update_cls.as_view(), name=f"{name}_update"),
        path(f"{slug}/<int:pk>/verwijderen/", delete_cls.as_view(), name=f"{name}_delete"),
    ]
