# Generated manually for ScheduledEmail recipients

from django.db import migrations, models
import django.db.models.deletion


def forwards_set_default_recipients(apps, schema_editor):
    ScheduledEmail = apps.get_model("tfk_mentors", "ScheduledEmail")
    for se in ScheduledEmail.objects.all():
        practice = se.practices.order_by("date").first()
        if practice:
            se.recipient_mode = "all_in_season"
            se.recipient_season_id = practice.season_id
        else:
            se.recipient_mode = "specific_mentors"
            se.recipient_season_id = None
        se.save(update_fields=["recipient_mode", "recipient_season_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0009_scheduled_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledemail",
            name="recipient_mode",
            field=models.CharField(
                choices=[
                    ("all_in_season", "All mentors in season"),
                    ("specific_mentors", "Specific mentors"),
                ],
                default="all_in_season",
                help_text="Whether to email every mentor in a season or only selected mentors.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="scheduledemail",
            name="recipient_season",
            field=models.ForeignKey(
                blank=True,
                help_text="When recipient_mode is all_in_season, every mentor linked to this season is included.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scheduled_emails_all_mentors",
                to="tfk_mentors.season",
            ),
        ),
        migrations.AddField(
            model_name="scheduledemail",
            name="specific_mentors",
            field=models.ManyToManyField(
                blank=True,
                help_text="When recipient_mode is specific_mentors, only these mentors receive the email.",
                related_name="scheduled_emails_explicit",
                to="tfk_mentors.mentor",
            ),
        ),
        migrations.RunPython(forwards_set_default_recipients, migrations.RunPython.noop),
    ]
