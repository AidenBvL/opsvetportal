from django.db import migrations


def grant(apps, schema_editor):
    # Rollen die klanten mogen zien/bewerken krijgen hetzelfde recht op het adresboek.
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("core")
    app_config.models_module = True
    create_permissions(app_config, verbosity=0, apps=apps)
    app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for action in ("view", "add", "change", "delete"):
        perm = Permission.objects.filter(content_type__app_label="core", codename=f"{action}_address").first()
        if perm is None:
            continue
        for group in Group.objects.filter(permissions__content_type__app_label="core", permissions__codename=f"{action}_customer"):
            group.permissions.add(perm)


class Migration(migrations.Migration):
    dependencies = [("core", "0015_address"), ("auth", "0012_alter_user_first_name_max_length")]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
