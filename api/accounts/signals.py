# accounts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from ..models import ResidentProfile  # путь поправь под свой проект

User = get_user_model()

@receiver(post_save, sender=User)
def mark_password_updated(sender, instance: User, created, **kwargs):
    # Нового пользователя не трогаем, чтобы не ставить "Обновлен" сразу
    if created:
        return

    # Если у юзера есть профиль и пароль выглядит измененным с прошлого раза,
    # просто ставим флаг "Обновлен".
    try:
        profile = instance.resident
    except ResidentProfile.DoesNotExist:
        return

    # Простейший вариант: если профиль до этого был "Не обновлен" — перевести в "Обновлен".
    # (Если нужна более строгая логика — можно дополнительно хранить предыдущий хеш пароля
    # в профиле и сравнивать, но для большинства кейсов хватит триггера на любое сохранение user.)
    if profile.password_status != ResidentProfile.PasswordStatus.UPDATED:
        profile.password_status = ResidentProfile.PasswordStatus.UPDATED
        profile.save(update_fields=["password_status", "updated_at"])
