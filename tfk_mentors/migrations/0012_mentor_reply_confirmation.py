from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0011_mentor_email_reply"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledemailmentortoken",
            name="email_received_confirmed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="scheduledemailmentorpracticereply",
            name="pace",
            field=models.CharField(
                blank=True,
                choices=[
                    ("8-9", "8-9"),
                    ("9-10", "9-10"),
                    ("10-11", "10-11"),
                    ("11-12", "11-12"),
                    ("12-13", "12-13"),
                    ("13+", "13+"),
                ],
                default="",
                max_length=11,
            ),
        ),
    ]
