from datetime import timedelta

from django.db import migrations, models


def backfill_recipients_emailed_count(apps, schema_editor):
    ScheduledEmail = apps.get_model("tfk_mentors", "ScheduledEmail")
    ScheduledEmailMentorToken = apps.get_model(
        "tfk_mentors", "ScheduledEmailMentorToken"
    )
    for email in ScheduledEmail.objects.filter(task_completed_at__isnull=False):
        cutoff = email.task_completed_at + timedelta(minutes=1)
        count = ScheduledEmailMentorToken.objects.filter(
            scheduled_email_id=email.id,
            created_at__lte=cutoff,
        ).count()
        if count == 0:
            count = ScheduledEmailMentorToken.objects.filter(
                scheduled_email_id=email.id
            ).count()
        email.recipients_emailed_count = count
        email.save(update_fields=["recipients_emailed_count"])


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0016_alter_mentor_cell_phone_blank"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledemail",
            name="recipients_emailed_count",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="How many mentors received this email when it was sent.",
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_recipients_emailed_count,
            migrations.RunPython.noop,
        ),
    ]
