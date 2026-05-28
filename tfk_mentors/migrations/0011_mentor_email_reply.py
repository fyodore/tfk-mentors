# Generated manually for mentor email reply tokens

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0010_scheduled_email_recipients"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduledEmailMentorToken",
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
                    "token",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                (
                    "mentor",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="scheduled_email_tokens",
                        to="tfk_mentors.mentor",
                    ),
                ),
                (
                    "scheduled_email",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="mentor_tokens",
                        to="tfk_mentors.scheduledemail",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ScheduledEmailMentorPracticeReply",
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
                    "attendance",
                    models.CharField(
                        choices=[
                            ("attending", "Attending"),
                            ("not_attending", "Not attending"),
                            ("first_half", "First half"),
                            ("second_half", "Second half"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "mentor_token",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="practice_replies",
                        to="tfk_mentors.scheduledemailmentortoken",
                    ),
                ),
                (
                    "practice",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        to="tfk_mentors.practice",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddConstraint(
            model_name="scheduledemailmentortoken",
            constraint=models.UniqueConstraint(
                fields=("scheduled_email", "mentor"),
                name="unique_scheduled_email_mentor_token",
            ),
        ),
        migrations.AddConstraint(
            model_name="scheduledemailmentorpracticereply",
            constraint=models.UniqueConstraint(
                fields=("mentor_token", "practice"),
                name="unique_mentor_token_practice_reply",
            ),
        ),
    ]
