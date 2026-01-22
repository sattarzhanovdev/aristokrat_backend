from rest_framework import serializers
from .models import (
    SimpleUser, House, Entrance, Apartment, Device
)

class SimpleUserSerializer(serializers.ModelSerializer):
    # ===== из профиля =====
    approval_status = serializers.CharField(
        source="profile.approval_status",
        read_only=True
    )
    phone = serializers.CharField(
        source="profile.phone",
        read_only=True
    )
    house_number = serializers.IntegerField(
        source="profile.house_number",
        read_only=True
    )
    entrance_no = serializers.IntegerField(
        source="profile.entrance_no",
        read_only=True
    )
    apartment_no = serializers.CharField(
        source="profile.apartment_no",
        read_only=True
    )
    car_number = serializers.CharField(
        source="profile.car_number",
        read_only=True
    )

    class Meta:
        model = SimpleUser
        fields = (
            "id",
            "login",
            "name",
            "role",
            "is_active",

            # профиль
            "approval_status",
            "phone",
            "house_number",
            "entrance_no",
            "apartment_no",
            "car_number",
        )



class HouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = House
        fields = "__all__"


class EntranceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entrance
        fields = "__all__"


class ApartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Apartment
        fields = "__all__"


class ApartmentListSerializer(serializers.ModelSerializer):
    house = serializers.IntegerField(source="entrance.house.number", read_only=True)
    entrance = serializers.IntegerField(source="entrance.number", read_only=True)

    class Meta:
        model = Apartment
        fields = ["id", "house", "entrance", "number", "is_blocked"]
