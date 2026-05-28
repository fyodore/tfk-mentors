# Generated manually for ScheduledEmail

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0008_mentor_split_practice"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduledEmail",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "scheduled_send_at",
                    models.DateTimeField(
                        db_index=True,
                        help_text="Date and time when this email should go out.",
                    ),
                ),
                (
                    "task_completed_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the send task finished (null if not run yet).",
                        null=True,
                    ),
                ),
                (
                    "body_text",
                    models.TextField(
                        help_text=(
                            "Message template. Use {{ first_name }}, {{ last_name }}, "
                            "and {{ pace }}; they are replaced for each mentor when "
                            "the email is sent."
                        ),
                    ),
                ),
            ],
            options={
                "ordering": ["-scheduled_send_at", "-id"],
            },
        ),
        migrations.AddField(
            model_name="scheduledemail",
            name="practices",
            field=models.ManyToManyField(
                blank=True,
                help_text="Practices included or referenced in this email.",
                related_name="scheduled_emails",
                to="tfk_mentors.practice",
            ),
        ),
    ]
