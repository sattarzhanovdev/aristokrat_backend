from rest_framework import serializers
from django.contrib.auth.models import User
from .models import House, Entrance, Apartment, ResidentProfile
from django.contrib.auth import get_user_model

UserData = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    adminFlag = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id","username","first_name","last_name","email",
            "house_number","entrance_no","apartment_no","car_number","phone",
            "status",
            "adminFlag",           # ← новое поле
        ]

    def get_adminFlag(self, obj):
        return bool(obj.is_superuser or obj.is_staff)

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

class ApartmentSerializer(serializers.ModelSerializer):
    entrance_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Entrance.objects.all(), source="entrance"
    )
    entrance = EntranceSerializer(read_only=True)

    class Meta:
        model = Apartment
        fields = (
            "id", "number", "owner_name", "is_blocked",
            "note", "entrance", "entrance_id", "created_at", "updated_at", "phone"
        )

class ApartmentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Apartment
        fields = ("id", "number", "is_blocked")


User = get_user_model()

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
    # объединённый ответ для фронта
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    house_number = serializers.IntegerField(required=False, allow_null=True)
    entrance_no = serializers.IntegerField(required=False, allow_null=True)
    apartment_no = serializers.CharField(required=False, allow_blank=True)
    car_number = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(read_only=True)

    def to_representation(self, instance: UserData):
        prof, _ = ResidentProfile.objects.get_or_create(user=instance)
        data = {
            "id": instance.id,
            "username": instance.username,
            "first_name": instance.first_name,
            "last_name": instance.last_name,
            "email": instance.email,
            "house_number": prof.house_number,
            "entrance_no": prof.entrance_no,
            "apartment_no": prof.apartment_no,
            "car_number": prof.car_number,
            "phone": prof.phone or instance.username,  # если логин = телефон
            "status": "Активен" if (instance.is_active and prof.is_active_resident) else "Заблокирован",
        }
        return data

    def update(self, instance: UserData, validated_data):
        prof, _ = ResidentProfile.objects.get_or_create(user=instance)
        # обновляем только поля профиля
        for f in ["house_number", "entrance_no", "apartment_no", "car_number", "phone"]:
            if f in validated_data:
                setattr(prof, f, validated_data[f])
        prof.full_clean()
        prof.save()
        return instance