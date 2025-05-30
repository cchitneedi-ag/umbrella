# Generated by Django 4.2.16 on 2025-03-03 18:41

from django.db import migrations


def update_version(apps, schema):
    Constants = apps.get_model("core", "Constants")
    version = Constants.objects.get(key="version")
    version.value = "25.3.3"
    version.save()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0066_increment_version"),
    ]

    operations = [migrations.RunPython(update_version)]
