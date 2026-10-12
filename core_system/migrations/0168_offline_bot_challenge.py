from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0167_officer_action_pin'),
    ]

    operations = [
        migrations.CreateModel(
            name='OfflineBotChallenge',
            fields=[
                ('challenge_id', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('username', models.CharField(max_length=150)),
                ('salt', models.CharField(max_length=64)),
                ('difficulty', models.IntegerField(default=16)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'offline_bot_challenge',
                'indexes': [models.Index(fields=['username', 'expires_at'], name='obc_user_exp_idx')],
            },
        ),
    ]
