from django.db import migrations


def seed(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    from core.ports import DEFAULT_PORTS

    Port = apps.get_model("core", "Port")
    for locode, name, aliases in DEFAULT_PORTS:
        Port.objects.get_or_create(locode=locode, defaults={"name": name, "aliases": aliases})

    # Rollen die rederijen mogen zien/bewerken krijgen hetzelfde recht op havens.
    app_config = apps.get_app_config("core")
    app_config.models_module = True  # nodig om rechten al tijdens de migratie aan te maken
    create_permissions(app_config, verbosity=0, apps=apps)
    app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for action in ("view", "add", "change", "delete"):
        port_perm = Permission.objects.filter(content_type__app_label="core", codename=f"{action}_port").first()
        if port_perm is None:
            continue
        for group in Group.objects.filter(permissions__content_type__app_label="core",
                                          permissions__codename=f"{action}_shippingline"):
            group.permissions.add(port_perm)


class Migration(migrations.Migration):
    dependencies = [("core", "0009_port"), ("auth", "0012_alter_user_first_name_max_length"), ("contenttypes", "0002_remove_content_type_name")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
