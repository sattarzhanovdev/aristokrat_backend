from django.contrib import admin, messages
from .models import House, Entrance, Apartment, Device, MAX_ENTRANCES, ResidentProfile
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model

User = get_user_model()

@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = ("id","number")
    search_fields = ("number",)

@admin.register(Entrance)
class EntranceAdmin(admin.ModelAdmin):
    list_display = ("id","house","number")
    list_filter = ("house",)

@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = ("id","number","entrance","is_blocked","owner_name")
    list_filter = ("entrance__house","entrance","is_blocked")
    search_fields = ("number","owner_name")


# apartments/admin.py
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "entrance_no", "state", "updated_at")
    list_editable = ("state",)
    list_filter = ("kind", "entrance_no", "state")
    search_fields = ("kind",)
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

    @admin.action(description="Сгенерировать устройства для 8 подъездов (+ калитки, паркинг)")
    def seed_defaults(self, request, qs):
        created = 0
        for no in range(1, MAX_ENTRANCES + 1):
            for kind in ("door", "lift_pass", "lift_gruz"):
                obj, was = Device.objects.get_or_create(kind=kind, entrance_no=no)
                created += int(was)
        for kind in ("kalitka1","kalitka2","kalitka3","kalitka4","parking"):
            obj, was = Device.objects.get_or_create(kind=kind, entrance_no=None)
            created += int(was)
        self.message_user(request, f"Создано новых записей: {created}", level=messages.SUCCESS)


class ResidentProfileInline(admin.StackedInline):
    model = ResidentProfile
    can_delete = False
    fk_name = "user"
    extra = 0
    fieldsets = (
        (None, {
            "fields": (
                ("house_number", "entrance_no"),
                "apartment_no",
                "car_number",
                "phone",
                "is_active_resident",
            )
        }),
    )

class UserAdmin(BaseUserAdmin):
    inlines = (ResidentProfileInline,)

# пере-регистрируем User с inline
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(ResidentProfile)
class ResidentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "approval_status", "password_status", "house_number", "entrance_no", "apartment_no", "is_active_resident", "updated_at")
    list_filter  = ("approval_status", "password_status", "is_active_resident", "house_number", "entrance_no")
    search_fields = ("user__username", "user__email", "apartment_no", "car_number", "phone")

    actions = ["mark_approved", "mark_not_approved", "mark_pwd_updated", "mark_pwd_not_updated"]

    @admin.action(description="Отметить как Принят")
    def mark_approved(self, request, qs):
        qs.update(approval_status=ResidentProfile.ApprovalStatus.ACCEPTED)

    @admin.action(description="Отметить как Не принят")
    def mark_not_approved(self, request, qs):
        qs.update(approval_status=ResidentProfile.ApprovalStatus.NOT_ACCEPTED)

    @admin.action(description="Пароль: Обновлен")
    def mark_pwd_updated(self, request, qs):
        qs.update(password_status=ResidentProfile.PasswordStatus.UPDATED)

    @admin.action(description="Пароль: Не обновлен")
    def mark_pwd_not_updated(self, request, qs):
        qs.update(password_status=ResidentProfile.PasswordStatus.NOT_UPDATED)