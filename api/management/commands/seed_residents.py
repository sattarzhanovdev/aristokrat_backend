# api/management/commands/seed_residents.py

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import (
    House,
    Entrance,
    Apartment,
    SimpleUser,
    ResidentProfile,
)

ENTRANCE_RANGES = {
    1: (1, 40),
    2: (41, 98),
    3: (99, 136),
    4: (137, 176),
    5: (177, 220),
    6: (221, 264),
    7: (265, 308),
    8: (309, 352),
}


def entrance_for(apt: int) -> int | None:
    for en, (a, b) in ENTRANCE_RANGES.items():
        if a <= apt <= b:
            return en
    return None


class Command(BaseCommand):
    help = "Создаёт дом, подъезды, квартиры, SimpleUser и ResidentProfile"

    def add_arguments(self, parser):
        parser.add_argument(
            "--house",
            type=int,
            default=1,
            help="Номер дома (по умолчанию 1)",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        house_no = opts["house"]

        # ---------- Дом ----------
        house, _ = House.objects.get_or_create(number=house_no)
        self.stdout.write(self.style.SUCCESS(f"Дом №{house_no}: OK"))

        # ---------- Подъезды ----------
        entrances = {}
        for no in range(1, 9):
            ent, _ = Entrance.objects.get_or_create(house=house, number=no)
            entrances[no] = ent
        self.stdout.write(self.style.SUCCESS("Подъезды 1..8: OK"))

        # ---------- Квартиры ----------
        apartments = []
        for en, (a, b) in ENTRANCE_RANGES.items():
            for apt in range(a, b + 1):
                apartments.append(
                    Apartment(
                        entrance=entrances[en],
                        number=str(apt),
                    )
                )

        Apartment.objects.bulk_create(
            apartments,
            batch_size=500,
            ignore_conflicts=True,
        )
        self.stdout.write(self.style.SUCCESS("Квартиры: OK"))

        # ---------- Пользователи + профили ----------
        users = []
        profiles = []

        for en, (a, b) in ENTRANCE_RANGES.items():
            for apt in range(a, b + 1):
                en_calc = entrance_for(apt) or en
                login = f"{apt}-{en_calc}"

                user = SimpleUser(
                    login=login,
                    password=str(apt),          # ❗ НЕ хэшируем
                    role="resident",
                    is_active=True,
                )
                users.append(user)

        SimpleUser.objects.bulk_create(
            users,
            batch_size=300,
            ignore_conflicts=True,
        )

        created_users = SimpleUser.objects.filter(
            login__regex=r"^\d+-\d+$"
        )

        for user in created_users:
            apt_str, en_str = user.login.split("-", 1)

            profiles.append(
                ResidentProfile(
                    user=user,
                    approval_status="accepted",
                    house_number=house_no,
                    entrance_no=int(en_str),
                    apartment_no=apt_str,
                    car_number="",
                    phone="",
                )
            )

        ResidentProfile.objects.bulk_create(
            profiles,
            batch_size=500,
            ignore_conflicts=True,
        )

        self.stdout.write(
            self.style.SUCCESS(f"Создано пользователей: {len(users)}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Создано профилей: {len(profiles)}")
        )

        self.stdout.write(
            self.style.WARNING(
                "Логин: '<квартира>-<подъезд>', Пароль: '<квартира>'  (пример: 125-3 / 125)"
            )
        )
