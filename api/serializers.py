# api/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import House, Entrance, Apartment, ResidentProfile

User = get_user_model()

# ======================= User / Profile =======================

class UserSerializer(serializers.ModelSerializer):
    # агрегированный флаг админа
    adminFlag = serializers.SerializerMethodField()

    # профильные поля как вычисляемые поля
    house_number = serializers.SerializerMethodField()
    entrance_no  = serializers.SerializerMethodField()
    apartment_no = serializers.SerializerMethodField()
    car_number   = serializers.SerializerMethodField()
    phone        = serializers.SerializerMethodField()
    status       = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email",
            # профиль:
            "house_number", "entrance_no", "apartment_no", "car_number", "phone", "status",
            # флаг админа:
            "adminFlag",
        ]

    def get_adminFlag(self, obj):
        return bool(obj.is_superuser or obj.is_staff)

    def _resident(self, obj):
        try:
            return obj.resident
        except ResidentProfile.DoesNotExist:
            return None

    def get_house_number(self, obj):
        rp = self._resident(obj)
        return rp.house_number if rp else None

    def get_entrance_no(self, obj):
        rp = self._resident(obj)
        return rp.entrance_no if rp else None

    def get_apartment_no(self, obj):
        rp = self._resident(obj)
        return rp.apartment_no if rp else ""

    def get_car_number(self, obj):
        rp = self._resident(obj)
        return rp.car_number if rp else ""

    def get_phone(self, obj):
        rp = self._resident(obj)
        # если телефона в профиле нет, можно вернуть пусто или username (если это телефон)
        return rp.phone if (rp and rp.phone) else ""

    def get_status(self, obj):
        rp = self._resident(obj)
        if rp is None:
            # если профиля нет — считаем активным
            return "Активен" if obj.is_active else "Заблокирован"
        return "Активен" if (obj.is_active and rp.is_active_resident) else "Заблокирован"


# ======================= House / Entrance =======================

class HouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = House
        fields = ("id", "number")

class EntranceSerializer(serializers.ModelSerializer):
    house = HouseSerializer(read_only=True)
    house_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=House.objects.all(), source="house"
    )

    class Meta:
        model = Entrance
        fields = ("id", "number", "house", "house_id")


# ======================= Apartment =======================

class ApartmentSerializer(serializers.ModelSerializer):
    entrance_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Entrance.objects.all(), source="entrance"
    )
    entrance = EntranceSerializer(read_only=True)

    # телефон жильца, найденный по связке дом/подъезд/квартира
    phone = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Apartment
        fields = (
            "id", "number", "owner_name", "is_blocked",
            "note", "entrance", "entrance_id",
            "created_at", "updated_at",
            "phone",
        )

    def get_phone(self, obj: Apartment) -> str:
        """
        Ищем телефон в ResidentProfile по связке:
          house_number == obj.entrance.house.number
          entrance_no  == obj.entrance.number
          apartment_no == obj.number  (с учётом ведущих нулей)
          is_active_resident == True
        Берём самый свежий непустой телефон.
        Портируемо (без TRIM в SQL), работает на SQLite/PostgreSQL/MySQL.
        """
        try:
            house_no = obj.entrance.house.number
            entr_no  = obj.entrance.number
            apt_num  = (obj.number or "").strip()
            apt_norm = apt_num.lstrip("0") or "0"

            qs = (
                ResidentProfile.objects
                .filter(
                    house_number=house_no,
                    entrance_no=entr_no,
                    is_active_resident=True,
                )
                .exclude(phone__isnull=True)
                .exclude(phone__exact="")
                .order_by("-updated_at")
                .values_list("phone", "apartment_no")
            )

            # 1) точное совпадение
            for phone, ap in qs:
                if (ap or "").strip() == apt_num:
                    return phone

            # 2) совпадение по нормализованному номеру (без ведущих нулей)
            for phone, ap in qs:
                ap_norm = (ap or "").strip().lstrip("0") or "0"
                if ap_norm == apt_norm:
                    return phone

            return ""
        except Exception:
            return ""


class ApartmentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Apartment
        fields = ("id", "number", "is_blocked")


# ======================= Profile (me) =======================

class ResidentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResidentProfile
        fields = (
            "house_number",
            "entrance_no",
            "apartment_no",
            "car_number",
            "phone",
            "is_active_resident",
        )

class ProfileMeSerializer(serializers.Serializer):
    """
    Объединённый сериалайзер для /api/profile/me (как в твоём коде).
    Если хочешь позволить обновлять first_name/last_name/email — сделай их writeable.
    """
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    house_number = serializers.IntegerField(required=False, allow_null=True)
    entrance_no = serializers.IntegerField(required=False, allow_null=True)
    apartment_no = serializers.CharField(required=False, allow_blank=True)
    car_number = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(read_only=True)

    def to_representation(self, instance: User):
        prof, _ = ResidentProfile.objects.get_or_create(user=instance)
        return {
            "id": instance.id,
            "username": instance.username,
            "first_name": instance.first_name or "",
            "last_name": instance.last_name or "",
            "email": instance.email or "",
            "house_number": prof.house_number,
            "entrance_no": prof.entrance_no,
            "apartment_no": prof.apartment_no or "",
            "car_number": prof.car_number or "",
            "phone": prof.phone or "",
            "status": "Активен" if (instance.is_active and prof.is_active_resident) else "Заблокирован",
        }

    def update(self, instance: User, validated_data):
        # даём возможность обновить базовые поля юзера
        for uf in ("first_name", "last_name", "email"):
            if uf in validated_data:
                setattr(instance, uf, validated_data[uf])
        instance.save()

        # и профиль
        prof, _ = ResidentProfile.objects.get_or_create(user=instance)
        for f in ["house_number", "entrance_no", "apartment_no", "car_number", "phone"]:
            if f in validated_data:
                setattr(prof, f, validated_data[f])
        prof.full_clean()
        prof.save()
        return instance
