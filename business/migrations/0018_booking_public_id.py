import uuid
from django.db import migrations, models


def populate_public_ids(apps, schema_editor):
    Booking = apps.get_model('business', 'Booking')
    db = schema_editor.connection.alias
    for pk in Booking.objects.using(db).filter(public_id__isnull=True).values_list('pk', flat=True).iterator():
        Booking.objects.using(db).filter(pk=pk).update(public_id=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [('business', '0017_company_fraud_blocked')]
    operations = [
        migrations.AddField(model_name='booking', name='public_id', field=models.UUIDField(null=True, unique=True, editable=False)),
        migrations.RunPython(populate_public_ids, migrations.RunPython.noop),
        migrations.AlterField(model_name='booking', name='public_id', field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
    ]
