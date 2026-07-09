from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tfk_mentors", "0030_practice_show_to_mentors"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mentorpracticeshowup",
            name="show_up",
            field=models.CharField(
                choices=[
                    ("attended", "Attended"),
                    ("missed", "Missed"),
                    ("found_replacement", "Found Replacement"),
                ],
                max_length=20,
            ),
        ),
    ]
