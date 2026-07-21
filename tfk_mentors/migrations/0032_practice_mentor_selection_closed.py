from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tfk_mentors", "0031_show_up_found_replacement"),
    ]

    operations = [
        migrations.AddField(
            model_name="practice",
            name="mentor_selection_closed_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "When set, At Practice mentors can no longer change replies for this "
                    "practice via their email link (set when the schedule is applied)."
                ),
                null=True,
            ),
        ),
    ]
