from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q

# ---------- USERS ----------

class SimpleUser(models.Model):
    login = models.CharField(max_length=64, unique=True)
    password = models.CharField(max_length=128)  # НЕ хэшируем
    name = models.CharField(max_length=128, blank=True)
    role = models.CharField(
        max_length=32,
        choices=[("admin", "Admin"), ("resident", "Resident")],
        default="resident"
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.login


class ResidentProfile(models.Model):
    user = models.OneToOneField(SimpleUser, on_delete=models.CASCADE, related_name="profile")

    approval_status = models.CharField(
        max_length=20,
        choices=[("accepted", "Принят"), ("not_accepted", "Не принят")],
        default="not_accepted"
    )

    house_number = models.PositiveIntegerField(null=True, blank=True)
    entrance_no = models.PositiveSmallIntegerField(null=True, blank=True)
    apartment_no = models.CharField(max_length=10, blank=True)
    car_number = models.CharField(max_length=32, blank=True)
    phone = models.CharField(max_length=32, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# ---------- HOUSES ----------

class House(models.Model):
    number = models.PositiveIntegerField(unique=True)

    def __str__(self):
        return f"Дом {self.number}"


class Entrance(models.Model):
    house = models.ForeignKey(House, on_delete=models.CASCADE, related_name="entrances")
    number = models.PositiveIntegerField()

    class Meta:
        unique_together = ("house", "number")


class Apartment(models.Model):
    entrance = models.ForeignKey(Entrance, on_delete=models.PROTECT, related_name="apartments")
    number = models.CharField(max_length=10)
    owner_name = models.CharField(max_length=200, blank=True)
    is_blocked = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("entrance", "number")
        ordering = ["id"]


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

    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    entrance_no = models.PositiveSmallIntegerField(null=True, blank=True)
    state = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("kind", "entrance_no")
        constraints = [
            models.CheckConstraint(
                name="device_entrance_rules",
                condition=(
                    Q(kind__in=["door", "lift_pass", "lift_gruz"], entrance_no__isnull=False)
                    | Q(kind__in=["kalitka1", "kalitka2", "kalitka3", "kalitka4", "parking"], entrance_no__isnull=True)
                ),
            )
        ]
