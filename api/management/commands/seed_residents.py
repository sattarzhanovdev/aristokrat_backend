# api/management/commands/seed_residents.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.test.utils import override_settings
from django.contrib.auth.hashers import make_password

from api.models import House, Entrance, Apartment

User = get_user_model()

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

class Command(BaseCommand):
    help = "Дом №1, подъезды 1..8, квартиры 1..352 и пользователи: username='квартира-подъезд', пароль='квартира'"

    def add_arguments(self, parser):
        parser.add_argument("--house", type=int, default=1)
        parser.add_argument("--reset-passwords", action="store_true",
                            help="Переустановить пароли существующим пользователям")
        parser.add_argument("--fast-hash", action="store_true",
                            help="Временный быстрый хеш (MD5) только на время сидирования")

    @transaction.atomic
    def handle(self, *args, **opts):
        house_no = opts["house"]
        reset_pw = opts["reset_passwords"]
        use_fast = opts["fast_hash"]

        ctx = (
            override_settings(
                PASSWORD_HASHERS=[
                    "django.contrib.auth.hashers.MD5PasswordHasher",
                ]
            )
            if use_fast
            else nullcontext()
        )

        with ctx:
            self._run(house_no, reset_pw)

    def _run(self, house_no: int, reset_pw: bool):
        house, _ = House.objects.get_or_create(number=house_no)
        self.stdout.write(self.style.SUCCESS(f"Дом №{house_no}: OK"))

        entrances = {}
        for no in range(1, 9):
            ent, _ = Entrance.objects.get_or_create(house=house, number=no)
            entrances[no] = ent
        self.stdout.write(self.style.SUCCESS("Подъезды 1..8: OK"))

        # --- Квартиры: создаём только отсутствующие, пачками
        want_apts = []
        for ent_no, (start, end) in ENTRANCE_RANGES.items():
            for apt_no in range(start, end + 1):
                want_apts.append((ent_no, apt_no))

        existing = set(
            Apartment.objects.filter(
                entrance__house=house, number__in=[a for _, a in want_apts]
            ).values_list("entrance__number", "number")
        )

        to_create = [
            Apartment(entrance=entrances[ent_no], number=apt_no)
            for (ent_no, apt_no) in want_apts
            if (ent_no, apt_no) not in existing
        ]
        if to_create:
            Apartment.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"Квартиры: создано {len(to_create)}, всего {len(want_apts)}"))

        # --- Пользователи: создаём отсутствующих пачками
        usernames = [f"{apt_no}-{ent_no}" for ent_no, (s, e) in ENTRANCE_RANGES.items() for apt_no in range(s, e + 1)]
        existing_users = set(User.objects.filter(username__in=usernames).values_list("username", flat=True))

        to_create_users = []
        for ent_no, (start, end) in ENTRANCE_RANGES.items():
            for apt_no in range(start, end + 1):
                username = f"{apt_no}-{ent_no}"
                if username in existing_users:
                    continue
                # пароли сразу хешуем (быстро, если --fast-hash)
                pwd_hash = make_password(str(apt_no))
                u = User(
                    username=username,
                    is_active=True,
                    password=pwd_hash,
                )
                # профильные поля, если они на User
                if hasattr(u, "house_number"):
                    u.house_number = house_no
                if hasattr(u, "entrance_no"):
                    u.entrance_no = ent_no
                if hasattr(u, "apartment_no"):
                    u.apartment_no = apt_no
                if hasattr(u, "car_number"):
                    u.car_number = "NO"
                if hasattr(u, "status"):
                    try:
                        u.status = "АКТИВЕН"
                    except Exception:
                        pass
                to_create_users.append(u)

        if to_create_users:
            User.objects.bulk_create(to_create_users, batch_size=300, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"Пользователи: создано {len(to_create_users)}, всего {len(usernames)}"))

        # --- По желанию переустановим пароли существующим
        if reset_pw:
            # обновим пароли порциями (без set_password для скорости)
            upd = []
            for ent_no, (start, end) in ENTRANCE_RANGES.items():
                for apt_no in range(start, end + 1):
                    username = f"{apt_no}-{ent_no}"
                    if username in existing_users:
                        upd.append((username, make_password(str(apt_no))))
            # батчевый апдейт
            if upd:
                # нет прямого bulk_update для разных значений password — делаем циклом, но только по существующим
                for i, (username, pwd) in enumerate(upd, 1):
                    User.objects.filter(username=username).update(password=pwd)
                    if i % 200 == 0:
                        self.stdout.write(f"Обновлено паролей: {i}/{len(upd)}")
                self.stdout.write(self.style.SUCCESS(f"Паролей обновлено: {len(upd)}"))

        self.stdout.write(self.style.WARNING(
            "Логин: '<квартира>-<подъезд>', Пароль: '<квартира>' (пример: 125-3 / 125)"
        ))


# для override_settings(None) совместимо с Python <3.10
from contextlib import contextmanager
@contextmanager
def nullcontext():
    yield
