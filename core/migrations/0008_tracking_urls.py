from django.db import migrations

# Publieke trackingpagina's van rederijen. {number} = B/L of boeking, {container} = containernummer.
URLS = {
    "MAEU": "https://www.maersk.com/tracking/{number}",
    "HLCU": "https://www.hapag-lloyd.com/en/online-business/track/track-by-container-solution.html?container={container}",
    "CMDU": "https://www.cma-cgm.com/ebusiness/tracking/search",
    "MSCU": "https://www.msc.com/en/track-a-shipment",
}


def fill(apps, schema_editor):
    ShippingLine = apps.get_model("core", "ShippingLine")
    for scac, url in URLS.items():
        ShippingLine.objects.filter(scac=scac, tracking_url_template="").update(tracking_url_template=url)


class Migration(migrations.Migration):
    dependencies = [("core", "0007_detail_fields")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
