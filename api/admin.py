from django.contrib import admin, messages
from django.db import models

from .models import (
    SimpleUser,
    ResidentProfile,
    House,
    Entrance,
    Apartment,
    Device,
    MAX_ENTRANCES,
)

# =========================
# USERS
# =========================

class ResidentProfileInline(admin.StackedInline):
    model = ResidentProfile
    can_delete = False
    extra = 0
    fieldsets = (
        ("Статус", {
            "fields": ("approval_status",)
        }),
        ("Адрес", {
            "fields": (
                ("house_number", "entrance_no"),
                "apartment_no",
            )
        }),
        ("Контакты", {
            "fields": ("car_number", "phone")
        }),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(SimpleUser)
class SimpleUserAdmin(admin.ModelAdmin):
    list_display = ("login", "name", "get_role_display", "is_active", "has_parking", "created_at")
    search_fields = ("login", "name")
    list_filter = ("role", "is_active", "has_parking", "created_at")
    ordering = ("-created_at",)

    inlines = (ResidentProfileInline,)

    fieldsets = (
        ("Учётные данные", {
            "fields": (
                "login",
                "password",
                "name",
            )
        }),
        ("Права и статус", {
            "fields": (
                "role",
                "is_active",
                "has_parking",
            )
        }),
        ("История", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(ResidentProfile)
class ResidentProfileAdmin(admin.ModelAdmin):
    list_display = (
        "get_user_name",
        "get_approval_status_display",
        "house_number",
        "entrance_no",
        "apartment_no",
        "phone",
    )
    list_filter = (
        "approval_status",
        "house_number",
        "entrance_no",
        "created_at",
    )
    search_fields = (
        "user__login",
        "user__name",
        "apartment_no",
        "car_number",
        "phone",
    )

    actions = ["mark_approved", "mark_not_approved"]

    fieldsets = (
        ("Пользователь", {
            "fields": ("user",)
        }),
        ("Статус", {
            "fields": ("approval_status",)
        }),
        ("Адрес проживания", {
            "fields": (
                ("house_number", "entrance_no"),
                "apartment_no",
            )
        }),
        ("Контакты", {
            "fields": ("phone", "car_number")
        }),
        ("История", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("created_at", "updated_at")

    def get_user_name(self, obj):
        return f"{obj.user.name or obj.user.login}"
    get_user_name.short_description = "Пользователь"

    @admin.action(description="✅ Одобрить выбранные")
    def mark_approved(self, request, qs):
        updated = qs.update(approval_status="accepted")
        self.message_user(request, f"Одобрено: {updated}", level=messages.SUCCESS)

    @admin.action(description="❌ Отклонить выбранные")
    def mark_not_approved(self, request, qs):
        updated = qs.update(approval_status="not_accepted")
        self.message_user(request, f"Отклонено: {updated}", level=messages.WARNING)


# =========================
# HOUSES & APARTMENTS
# =========================

class EntranceInline(admin.TabularInline):
    model = Entrance
    extra = 0
    fields = ("number",)


class ApartmentInline(admin.TabularInline):
    model = Apartment
    extra = 0
    fields = ("number", "owner_name", "is_blocked")


@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = ("number", "get_entrances_count", "get_apartments_count")
    search_fields = ("number",)
    inlines = (EntranceInline,)

    fieldsets = (
        ("Основная информация", {
            "fields": ("number",)
        }),
    )

    def get_entrances_count(self, obj):
        return obj.entrances.count()
    get_entrances_count.short_description = "Подъездов"

    def get_apartments_count(self, obj):
        return obj.entrances.aggregate(
            total=models.Count("apartments")
        )["total"]
    get_apartments_count.short_description = "Квартир"


@admin.register(Entrance)
class EntranceAdmin(admin.ModelAdmin):
    list_display = ("__str__", "house", "number", "get_apartments_count")
    list_filter = ("house",)
    inlines = (ApartmentInline,)

    fieldsets = (
        ("Информация", {
            "fields": ("house", "number")
        }),
    )

    def get_apartments_count(self, obj):
        return obj.apartments.count()
    get_apartments_count.short_description = "Квартир"


@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "entrance", "owner_name", "is_blocked")
    list_filter = ("entrance__house", "entrance", "is_blocked", "created_at")
    search_fields = ("number", "owner_name")

    fieldsets = (
        ("Расположение", {
            "fields": ("entrance", "number")
        }),
        ("Информация о владельце", {
            "fields": ("owner_name",)
        }),
        ("Статус", {
            "fields": ("is_blocked", "note")
        }),
        ("История", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("created_at", "updated_at")


# =========================
# DEVICES
# =========================

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("__str__", "get_kind_display", "entrance_no", "state", "updated_at")
    list_editable = ("state",)
    list_filter = ("kind", "entrance_no", "state", "updated_at")
    ordering = ("entrance_no", "kind")

    actions = ["make_on", "make_off", "seed_defaults"]

    fieldsets = (
        ("Параметры", {
            "fields": ("kind", "entrance_no", "state")
        }),
        ("История", {
            "fields": ("updated_at",),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("updated_at",)

    @admin.action(description="🟢 Включить выбранные")
    def make_on(self, request, qs):
        updated = qs.update(state=True)
        self.message_user(request, f"Включено: {updated}", level=messages.SUCCESS)

    @admin.action(description="🔴 Выключить выбранные")
    def make_off(self, request, qs):
        updated = qs.update(state=False)
        self.message_user(request, f"Выключено: {updated}", level=messages.WARNING)

    @admin.action(description="🔄 Генерировать устройства по умолчанию")
    def seed_defaults(self, request, qs):
        created = 0

        # Двери и лифты для каждого подъезда
        for no in range(1, MAX_ENTRANCES + 1):
            for kind in ("door", "lift_pass", "lift_gruz"):
                _, was = Device.objects.get_or_create(kind=kind, entrance_no=no)
                created += int(was)

        # Калитки и паркинг (без привязки к подъезду)
        for kind in ("kalitka1", "kalitka2", "kalitka3", "kalitka4", "parking"):
            _, was = Device.objects.get_or_create(kind=kind, entrance_no=None)
            created += int(was)

        self.message_user(
            request,
            f"✅ Создано новых устройств: {created}",
            level=messages.SUCCESS
        )
