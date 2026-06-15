from django.db import migrations, models


def set_latest_season_current(apps, schema_editor):
    Season = apps.get_model("tfk_mentors", "Season")
    latest = Season.objects.order_by("-year", "-id").first()
    if latest is not None:
        Season.objects.filter(is_current=True).update(is_current=False)
        latest.is_current = True
        latest.save(update_fields=["is_current"])


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0018_scheduledemailmentortoken_included_in_send"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="is_current",
            field=models.BooleanField(
                default=False,
                help_text="When true, this season is the active season for the app.",
            ),
        ),
        migrations.RunPython(set_latest_season_current, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="season",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_current", True)),
                fields=("is_current",),
                name="unique_current_season",
            ),
        ),
    ]
