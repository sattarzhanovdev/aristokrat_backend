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