from datetime import timedelta

from django.db import migrations, models


def backfill_included_in_send(apps, schema_editor):
    ScheduledEmail = apps.get_model("tfk_mentors", "ScheduledEmail")
    ScheduledEmailMentorToken = apps.get_model(
        "tfk_mentors", "ScheduledEmailMentorToken"
    )
    for email in ScheduledEmail.objects.filter(task_completed_at__isnull=False):
        cutoff = email.task_completed_at + timedelta(minutes=1)
        ScheduledEmailMentorToken.objects.filter(
            scheduled_email_id=email.id,
            created_at__lte=cutoff,
        ).update(included_in_send=True)


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0017_scheduledemail_recipients_emailed_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledemailmentortoken",
            name="included_in_send",
            field=models.BooleanField(
                default=False,
                help_text="True when this mentor was emailed as part of the send.",
            ),
        ),
        migrations.RunPython(
            backfill_included_in_send,
            migrations.RunPython.noop,
        ),
    ]
