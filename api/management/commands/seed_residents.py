# api/management/commands/seed_residents.py
from contextlib import contextmanager
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.test.utils import override_settings

from api.models import House, Entrance, Apartment, ResidentProfile

User = get_user_model()

# Диапазоны квартир для каждого подъезда
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


@contextmanager
def nullcontext():
    """override_settings(None) для старых версий Python."""
    yield


def entrance_for(apt: int) -> int | None:
    for en, (a, b) in ENTRANCE_RANGES.items():
        if a <= apt <= b:
            return en
    return None


class Command(BaseCommand):
    help = (
        "Создаёт: дом, подъезды 1..8, квартиры и пользователей вида "
        "'<квартира>-<подъезд>' (пароль '<квартира>'), а также ResidentProfile."
    )

    def add_arguments(self, parser):
        parser.add_argument("--house", type=int, default=1, help="Номер дома (по умолчанию 1)")
        parser.add_argument(
            "--fast-hash",
            action="store_true",
            help="Временный лёгкий хеш (MD5) только на время сидирования."
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Переустановить пароли существующим пользователям (медленно с обычным хешем)."
        )
        parser.add_argument(
            "--reset-profiles",
            action="store_true",
            help="Обновить поля существующих ResidentProfile."
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        house_no: int = opts["house"]
        use_fast: bool = opts["fast_hash"]
        reset_pw: bool = opts["reset_passwords"]
        reset_profiles: bool = opts["reset_profiles"]

        # На время сидирования можно упростить хеширование
        ctx = (
            override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
            if use_fast else nullcontext()
        )

        with ctx:
            self._run(house_no, reset_pw, reset_profiles)

    # --- Основная логика -----------------------------------------------------

    def _run(self, house_no: int, reset_pw: bool, reset_profiles: bool):
        # Дом
        house, _ = House.objects.get_or_create(number=house_no)
        self.stdout.write(self.style.SUCCESS(f"Дом №{house_no}: OK"))

        # Подъезды
        entrances = {}
        for no in range(1, 9):
            ent, _ = Entrance.objects.get_or_create(house=house, number=no)
            entrances[no] = ent
        self.stdout.write(self.style.SUCCESS("Подъезды 1..8: OK"))

        # Квартиры (bulk_create только для отсутствующих)
        want_apts = [(en, apt) for en, (a, b) in ENTRANCE_RANGES.items() for apt in range(a, b + 1)]
        existing_pairs = set(
            Apartment.objects.filter(
                entrance__house=house,
                number__in=[a for _, a in want_apts],
            ).values_list("entrance__number", "number")
        )

        to_create_apts = [
            Apartment(entrance=entrances[en], number=apt)
            for en, apt in want_apts
            if (en, apt) not in existing_pairs
        ]
        if to_create_apts:
            Apartment.objects.bulk_create(to_create_apts, batch_size=500, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"Квартиры: создано {len(to_create_apts)}, всего {len(want_apts)}"))

        # Пользователи (bulk_create только новых)
        usernames = [f"{apt}-{en}" for en, (a, b) in ENTRANCE_RANGES.items() for apt in range(a, b + 1)]
        existing_users = set(User.objects.filter(username__in=usernames).values_list("username", flat=True))

        to_create_users = []
        for en, (a, b) in ENTRANCE_RANGES.items():
            for apt in range(a, b + 1):
                uname = f"{apt}-{en}"
                if uname in existing_users:
                    continue
                # пароль = номер квартиры
                pwd_hash = make_password(str(apt))
                u = User(username=uname, is_active=True, password=pwd_hash)
                to_create_users.append(u)

        if to_create_users:
            User.objects.bulk_create(to_create_users, batch_size=300, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"Пользователи: создано {len(to_create_users)}, всего {len(usernames)}"))

        # По желанию: переустановить пароли существующим (медленно без --fast-hash)
        if reset_pw:
            upd = []
            for en, (a, b) in ENTRANCE_RANGES.items():
                for apt in range(a, b + 1):
                    uname = f"{apt}-{en}"
                    if uname in existing_users:
                        upd.append((uname, make_password(str(apt))))
            for i, (uname, pwd) in enumerate(upd, 1):
                User.objects.filter(username=uname).update(password=pwd)
                if i % 200 == 0:
                    self.stdout.write(f"Обновлено паролей: {i}/{len(upd)}")
            self.stdout.write(self.style.SUCCESS(f"Паролей обновлено: {len(upd)}"))

        # Профили жильцов (создать отсутствующие пачкой)
        all_users_qs = User.objects.filter(username__in=usernames).only("id", "username")
        uname_to_user = {u.username: u for u in all_users_qs}

        existing_profile_usernames = set(
            ResidentProfile.objects.filter(user__in=all_users_qs)
            .values_list("user__username", flat=True)
        )

        to_create_profiles = []
        for uname, user in uname_to_user.items():
            if uname in existing_profile_usernames:
                continue
            try:
                apt_str, en_str = uname.split("-", 1)
                apt_no = int(apt_str)
                en_no = int(en_str)
            except Exception:
                continue
            # подстрахуемся правилом диапазонов
            en_calc = entrance_for(apt_no)
            if en_calc and en_calc != en_no:
                en_no = en_calc

            to_create_profiles.append(
                ResidentProfile(
                    user=user,
                    house_number=house_no,
                    entrance_no=en_no,
                    apartment_no=apt_no,
                    car_number="NO",
                    phone="",
                    is_active_resident=True,
                )
            )

        if to_create_profiles:
            ResidentProfile.objects.bulk_create(to_create_profiles, batch_size=500, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"Профили: создано {len(to_create_profiles)}"))

        # Обновить существующие профили (если попросили)
        if reset_profiles:
            updated = 0
            for uname in existing_profile_usernames:
                user = uname_to_user.get(uname)
                if not user:
                    continue
                try:
                    apt_str, en_str = uname.split("-", 1)
                    apt_no = int(apt_str)
                    en_no = int(en_str)
                except Exception:
                    continue
                en_calc = entrance_for(apt_no)
                if en_calc and en_calc != en_no:
                    en_no = en_calc

                ResidentProfile.objects.filter(user=user).update(
                    house_number=house_no,
                    entrance_no=en_no,
                    apartment_no=apt_no,
                    car_number="NO",
                    phone="",
                    is_active_resident=True,
                )
                updated += 1
            self.stdout.write(self.style.SUCCESS(f"Профили: обновлено {updated}"))

        self.stdout.write(self.style.WARNING(
            "Логин: '<квартира>-<подъезд>', Пароль: '<квартира>'  (пример: 125-3 / 125)"
        ))
