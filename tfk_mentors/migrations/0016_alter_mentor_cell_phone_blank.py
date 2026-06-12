from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0015_alter_mentor_pace_blank"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mentor",
            name="cell_phone",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
