from django.contrib import admin

from .models import Invoice, Payment


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ("created_at", "amount", "method", "provider", "status", "note", "recorded_by")
    readonly_fields = fields
    can_delete = False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "user", "title", "period", "amount", "due_date", "block_on_overdue", "status", "created_at")
    list_filter = ("status", "block_on_overdue", "due_date")
    search_fields = ("title", "period", "user__login", "user__name", "user__profile__apartment_no")
    raw_id_fields = ("user", "created_by")
    inlines = (PaymentInline,)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "invoice", "amount", "method", "provider", "status", "created_at", "completed_at")
    list_filter = ("status", "method", "provider")
    raw_id_fields = ("invoice", "recorded_by")
