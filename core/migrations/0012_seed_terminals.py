from django.db import migrations


def seed(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    from core.ports import DEFAULT_TERMINALS

    Port = apps.get_model("core", "Port")
    Terminal = apps.get_model("core", "Terminal")
    for name, locode, aliases in DEFAULT_TERMINALS:
        Terminal.objects.get_or_create(name=name, defaults={"aliases": aliases, "port": Port.objects.filter(locode=locode).first()})

    # Rollen die havens mogen zien/bewerken krijgen hetzelfde recht op terminals.
    app_config = apps.get_app_config("core")
    app_config.models_module = True
    create_permissions(app_config, verbosity=0, apps=apps)
    app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for action in ("view", "add", "change", "delete"):
        perm = Permission.objects.filter(content_type__app_label="core", codename=f"{action}_terminal").first()
        if perm is None:
            continue
        for group in Group.objects.filter(permissions__content_type__app_label="core", permissions__codename=f"{action}_port"):
            group.permissions.add(perm)

    # Bestaande dossiers: terminalnamen gelijktrekken.
    from core.ports import clear_cache, terminal_name

    clear_cache()
    SeaShipment = apps.get_model("shipments", "SeaShipment")
    for pk, value in SeaShipment.objects.exclude(terminal="").values_list("pk", "terminal"):
        name = terminal_name(value)
        if name != value:
            SeaShipment.objects.filter(pk=pk).update(terminal=name)
    clear_cache()


class Migration(migrations.Migration):
    dependencies = [("core", "0011_terminal"), ("shipments", "0005_port_codes")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
