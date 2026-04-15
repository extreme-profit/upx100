from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def cleanup_employees_without_users(apps, schema_editor):
    """Удаление сотрудников без связанных пользователей"""
    Employee = apps.get_model('business', 'Employee')
    # Удаляем всех сотрудников без user (так как БД новая, это безопасно)
    Employee.objects.filter(user__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0004_alter_service_duration'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Сначала очищаем данные
        migrations.RunPython(cleanup_employees_without_users, reverse_code=migrations.RunPython.noop),
        
        # Изменяем поле user на non-nullable
        migrations.AlterField(
            model_name='employee',
            name='user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='employee_profile',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        
        # Удаляем старые поля
        migrations.RemoveField(
            model_name='employee',
            name='name',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='email',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='password',
        ),
        
        # Меняем unique_together
        migrations.AlterUniqueTogether(
            name='employee',
            unique_together={('company', 'user')},
        ),
    ]
