from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0003_add_extended_stats_to_aggregate'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerseasonaggregate',
            name='three_point_rate',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='playerseasonaggregate',
            name='free_throw_rate',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='playerseasonaggregate',
            name='tov_percent',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='playerseasonaggregate',
            name='mp_percent',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='playerseasonaggregate',
            name='orb_percent',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='playerseasonaggregate',
            name='drb_percent',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='playerseasonaggregate',
            name='ast_percent',
            field=models.FloatField(default=0.0),
        ),
    ]
