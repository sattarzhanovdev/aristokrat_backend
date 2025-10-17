from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.contrib.auth import get_user_model

class House(models.Model):
    number = models.PositiveIntegerField(unique=True)

    def __str__(self): return f"Дом {self.number}"

class Entrance(models.Model):
    house = models.ForeignKey(House, on_delete=models.CASCADE, related_name="entrances")
    number = models.PositiveIntegerField()  # подъезд/блок

    class Meta:
        unique_together = ("house", "number")

    def __str__(self): return f"{self.house} • Подъезд {self.number}"

class Apartment(models.Model):
    entrance = models.ForeignKey(Entrance, on_delete=models.PROTECT, related_name="apartments")
    number = models.CharField(max_length=10)    # "001", "12" и т.п.
    owner_name = models.CharField(max_length=200, blank=True)
    is_blocked = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("entrance", "number")
        ordering = ["id"]

    def __str__(self): return f"Кв. {self.number} ({self.entrance})"


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

    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    entrance_no = models.PositiveSmallIntegerField(null=True, blank=True)  # 1..8 для подъездов/лифтов
    state = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("kind", "entrance_no")
        ordering = ["entrance_no", "kind"]
        constraints = [
            # если kind подъездный — entrance_no обязателен
            models.CheckConstraint(
                name="entrance_required_for_entrance_kinds",
                check=Q(kind__in=["door", "lift_pass", "lift_gruz"], entrance_no__isnull=False)
                      | Q(kind__in=["kalitka1","kalitka2","kalitka3","kalitka4","parking"]),
            ),
            # если kind глобальный — entrance_no ДОЛЖЕН быть null
            models.CheckConstraint(
                name="no_entrance_for_global_kinds",
                check=Q(kind__in=["kalitka1","kalitka2","kalitka3","kalitka4","parking"], entrance_no__isnull=True)
                      | Q(kind__in=["door","lift_pass","lift_gruz"]),
            ),
        ]

    def clean(self):
        # валидируем номер подъезда
        if self.kind in {"door","lift_pass","lift_gruz"}:
            if self.entrance_no is None:
                raise ValidationError("Для этого типа нужно указать номер подъезда 1..8.")
            if not (1 <= int(self.entrance_no) <= MAX_ENTRANCES):
                raise ValidationError(f"Номер подъезда должен быть от 1 до {MAX_ENTRANCES}.")
        else:
            self.entrance_no = None  # для глобальных всегда null

    def __str__(self):
        scope = f"подъезд {self.entrance_no}" if self.entrance_no else "global"
        return f"{self.get_kind_display()} • {scope} = {self.state}"
      

User = get_user_model()

MAX_ENTRANCES = 8  # подъезды 1..8

class ResidentProfile(models.Model):
    class ApprovalStatus(models.TextChoices):
        ACCEPTED = "accepted", "Принят"
        NOT_ACCEPTED = "not_accepted", "Не принят"

    class PasswordStatus(models.TextChoices):
        UPDATED = "updated", "Обновлен"
        NOT_UPDATED = "not_updated", "Не обновлен"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="resident")

    # Статусы
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.NOT_ACCEPTED,
        db_index=True,
        verbose_name="Статус модерации",
        help_text="Принят / Не принят",
    )
    password_status = models.CharField(
        max_length=20,
        choices=PasswordStatus.choices,
        default=PasswordStatus.NOT_UPDATED,
        db_index=True,
        verbose_name="Статус пароля",
        help_text="Обновлен / Не обновлен",
    )

    # что просил: блок (дом), подъезд, квартира, номер машины
    house_number = models.PositiveIntegerField(null=True, blank=True, help_text="Блок/дом, напр. 18 или 20")
    entrance_no  = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Подъезд 1..8")
    apartment_no = models.CharField(max_length=10, blank=True, help_text="Номер квартиры, например 001 или 12")
    car_number   = models.CharField(max_length=32, blank=True, help_text="Госномер авто")

    # доп. поля
    phone = models.CharField(max_length=32, blank=True)
    is_active_resident = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Профиль жильца"
        verbose_name_plural = "Профили жильцов"

    def __str__(self):
        return f"Профиль {self.user} • {self.get_approval_status_display()} • {self.get_password_status_display()}"

    def clean(self):
        if self.entrance_no is not None and not (1 <= int(self.entrance_no) <= MAX_ENTRANCES):
            raise ValidationError(f"Подъезд должен быть от 1 до {MAX_ENTRANCES}.")