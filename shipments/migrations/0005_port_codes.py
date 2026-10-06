from django.db import migrations


def recode(apps, schema_editor):
    # Bestaande dossiers: havennamen ("PARANAGUA", "Rotterdam, Netherlands") omzetten naar UN/LOCODE.
    from core.ports import clear_cache, port_code

    clear_cache()
    SeaShipment = apps.get_model("shipments", "SeaShipment")
    for shipment in SeaShipment.objects.all().only("pk", "port_of_loading", "port_of_discharge"):
        pol, pod = port_code(shipment.port_of_loading), port_code(shipment.port_of_discharge) or "NLRTM"
        if (pol, pod) != (shipment.port_of_loading, shipment.port_of_discharge):
            SeaShipment.objects.filter(pk=shipment.pk).update(port_of_loading=pol, port_of_discharge=pod)
    clear_cache()


class Migration(migrations.Migration):
    dependencies = [("shipments", "0004_weight_decimals_package_type"), ("core", "0010_seed_ports")]

    operations = [migrations.RunPython(recode, migrations.RunPython.noop)]
