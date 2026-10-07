from django.db import migrations


def load(apps, schema_editor):
    # Alle UN/LOCODE-zeehavens en de SMDG Terminal Code List (core/data/*.csv).
    from core.ports import clear_cache, import_reference_data, recode_shipments

    import_reference_data(apps.get_model("core", "Port"), apps.get_model("core", "Terminal"), log=lambda message: None)
    clear_cache()
    recode_shipments(open_only=False)
    clear_cache()


class Migration(migrations.Migration):
    dependencies = [("core", "0013_terminal_details"), ("shipments", "0005_port_codes")]

    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
