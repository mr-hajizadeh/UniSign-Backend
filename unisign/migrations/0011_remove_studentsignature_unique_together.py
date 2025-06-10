from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('unisign', '0010_alter_studentsignature_unique_together_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='studentsignature',
            unique_together=set(),
        ),
    ] 