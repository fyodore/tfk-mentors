from django.db import migrations, models


def backfill_reply_mentor(apps, schema_editor):
    Reply = apps.get_model("tfk_mentors", "ScheduledEmailMentorPracticeReply")
    for reply in Reply.objects.select_related("mentor_token").iterator():
        reply.mentor_id = reply.mentor_token.mentor_id
        reply.save(update_fields=["mentor_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0012_mentor_reply_confirmation"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledemailmentorpracticereply",
            name="mentor",
            field=models.ForeignKey(
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="scheduled_email_practice_replies",
                to="tfk_mentors.mentor",
            ),
        ),
        migrations.RunPython(backfill_reply_mentor, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="scheduledemailmentorpracticereply",
            name="mentor",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="scheduled_email_practice_replies",
                to="tfk_mentors.mentor",
            ),
        ),
        migrations.AlterField(
            model_name="scheduledemailmentorpracticereply",
            name="practice",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="mentor_email_replies",
                to="tfk_mentors.practice",
            ),
        ),
    ]
