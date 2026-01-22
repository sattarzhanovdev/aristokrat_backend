from django.contrib import admin, messages

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
        (None, {
            "fields": (
                ("approval_status",),
                ("house_number", "entrance_no"),
                "apartment_no",
                "car_number",
                "phone",
            )
        }),
    )


@admin.register(SimpleUser)
class SimpleUserAdmin(admin.ModelAdmin):
    list_display = ("id", "login", "name", "role", "is_active", "created_at")
    search_fields = ("login", "name")
    list_filter = ("role", "is_active")
    ordering = ("id",)

    inlines = (ResidentProfileInline,)

    fieldsets = (
        (None, {
            "fields": ("login", "password", "name", "role", "is_active")
        }),
    )


@admin.register(ResidentProfile)
class ResidentProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "approval_status",
        "house_number",
        "entrance_no",
        "apartment_no",
        "phone",
        "updated_at",
    )
    list_filter = (
        "approval_status",
        "house_number",
        "entrance_no",
    )
    search_fields = (
        "user__login",
        "apartment_no",
        "car_number",
        "phone",
    )

    actions = ["mark_approved", "mark_not_approved"]

    @admin.action(description="Отметить как Принят")
    def mark_approved(self, request, qs):
        qs.update(approval_status="accepted")

    @admin.action(description="Отметить как Не принят")
    def mark_not_approved(self, request, qs):
        qs.update(approval_status="not_accepted")


# =========================
# HOUSES
# =========================

@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = ("id", "number")
    search_fields = ("number",)


@admin.register(Entrance)
class EntranceAdmin(admin.ModelAdmin):
    list_display = ("id", "house", "number")
    list_filter = ("house",)


@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "number", "entrance", "is_blocked", "owner_name")
    list_filter = ("entrance__house", "entrance", "is_blocked")
    search_fields = ("number", "owner_name")


# =========================
# DEVICES
# =========================

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "entrance_no", "state", "updated_at")
    list_editable = ("state",)
    list_filter = ("kind", "entrance_no", "state")
    ordering = ("entrance_no", "kind")

    actions = ["make_on", "make_off", "seed_defaults"]

    @admin.action(description="Включить выбранные")
    def make_on(self, request, qs):
        updated = qs.update(state=True)
        self.message_user(request, f"Обновлено: {updated}", level=messages.SUCCESS)

    @admin.action(description="Выключить выбранные")
    def make_off(self, request, qs):
        updated = qs.update(state=False)
        self.message_user(request, f"Обновлено: {updated}", level=messages.SUCCESS)

    @admin.action(description="Сгенерировать устройства (8 подъездов + калитки + паркинг)")
    def seed_defaults(self, request, qs):
        created = 0

        for no in range(1, MAX_ENTRANCES + 1):
            for kind in ("door", "lift_pass", "lift_gruz"):
                _, was = Device.objects.get_or_create(kind=kind, entrance_no=no)
                created += int(was)

        for kind in ("kalitka1", "kalitka2", "kalitka3", "kalitka4", "parking"):
            _, was = Device.objects.get_or_create(kind=kind, entrance_no=None)
            created += int(was)

        self.message_user(
            request,
            f"Создано новых устройств: {created}",
            level=messages.SUCCESS
        )
