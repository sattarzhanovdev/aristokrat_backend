from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q

# ---------- USERS ----------

class SimpleUser(models.Model):
    ROLE_CHOICES = [
        ("admin", "Админ"),
        ("resident", "Резидент"),
    ]
    
    login = models.CharField(max_length=64, unique=True, verbose_name="Логин")
    password = models.CharField(max_length=128, verbose_name="Пароль")  # НЕ хэшируем
    name = models.CharField(max_length=128, blank=True, verbose_name="Имя")
    role = models.CharField(
        max_length=32,
        choices=ROLE_CHOICES,
        default="resident",
        verbose_name="Роль"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    has_parking = models.BooleanField(default=False, verbose_name="Парковка")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.login} ({self.get_role_display()})"


class ResidentProfile(models.Model):
    APPROVAL_CHOICES = [
        ("accepted", "Принят"),
        ("not_accepted", "Не принят"),
    ]

    user = models.OneToOneField(SimpleUser, on_delete=models.CASCADE, related_name="profile", verbose_name="Пользователь")

    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_CHOICES,
        default="not_accepted",
        verbose_name="Статус одобрения"
    )

    house_number = models.PositiveIntegerField(null=True, blank=True, verbose_name="Номер дома")
    entrance_no = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Номер подъезда")
    apartment_no = models.CharField(max_length=10, blank=True, verbose_name="Номер квартиры")
    car_number = models.CharField(max_length=32, blank=True, verbose_name="Номер машины")
    phone = models.CharField(max_length=32, blank=True, verbose_name="Телефон")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Профиль резидента"
        verbose_name_plural = "Профили резидентов"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.name or self.user.login} - {self.get_approval_status_display()}"


# ---------- HOUSES ----------

class House(models.Model):
    number = models.PositiveIntegerField(unique=True, verbose_name="Номер дома")

    class Meta:
        verbose_name = "Дом"
        verbose_name_plural = "Дома"
        ordering = ["number"]

    def __str__(self):
        return f"Дом {self.number}"


class Entrance(models.Model):
    house = models.ForeignKey(House, on_delete=models.CASCADE, related_name="entrances", verbose_name="Дом")
    number = models.PositiveIntegerField(verbose_name="Номер подъезда")

    class Meta:
        unique_together = ("house", "number")
        verbose_name = "Подъезд"
        verbose_name_plural = "Подъезды"
        ordering = ["house", "number"]

    def __str__(self):
        return f"{self.house} - Подъезд {self.number}"


class Apartment(models.Model):
    entrance = models.ForeignKey(Entrance, on_delete=models.PROTECT, related_name="apartments", verbose_name="Подъезд")
    number = models.CharField(max_length=10, verbose_name="Номер квартиры")
    owner_name = models.CharField(max_length=200, blank=True, verbose_name="Имя владельца")
    is_blocked = models.BooleanField(default=False, verbose_name="Заблокирована")
    note = models.TextField(blank=True, verbose_name="Примечание")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        unique_together = ("entrance", "number")
        ordering = ["entrance", "id"]
        verbose_name = "Квартира"
        verbose_name_plural = "Квартиры"

    def __str__(self):
        return f"{self.entrance} - Кв. {self.number}"


# ---------- DEVICES ----------

MAX_ENTRANCES = 8

class Device(models.Model):
    KIND_CHOICES = [
        ("door", "Подъездная дверь"),
        ("lift_pass", "Лифт (пассажир)"),
        ("lift_gruz", "Лифт (грузовой)"),
        ("kalitka1", "Калитка №1"),
        ("kalitka2", "Калитка №2"),
        ("kalitka3", "Калитка №3"),
        ("kalitka4", "Калитка №4"),
        ("parking", "Паркинг"),
    ]

    kind = models.CharField(max_length=32, choices=KIND_CHOICES, verbose_name="Тип устройства")
    entrance_no = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Номер подъезда")
    state = models.BooleanField(default=False, verbose_name="Включено")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        unique_together = ("kind", "entrance_no")
        verbose_name = "Устройство"
        verbose_name_plural = "Устройства"
        ordering = ["entrance_no", "kind"]
        constraints = [
            models.CheckConstraint(
                name="device_entrance_rules",
                condition=(
                    Q(kind__in=["door", "lift_pass", "lift_gruz"], entrance_no__isnull=False)
                    | Q(kind__in=["kalitka1", "kalitka2", "kalitka3", "kalitka4", "parking"], entrance_no__isnull=True)
                ),
            )
        ]

    def __str__(self):
        kind_display = self.get_kind_display()
        if self.entrance_no:
            return f"{kind_display} (подъезд {self.entrance_no})"
        return kind_display
