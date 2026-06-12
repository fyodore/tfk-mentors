from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0014_alter_scheduledemail_body_text_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mentor",
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
