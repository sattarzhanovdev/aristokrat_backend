from decimal import Decimal

from rest_framework import serializers

from api.models import SimpleUser
from .models import Invoice, Payment, today


def _profile(user, attr, default=None):
    p = getattr(user, "profile", None)
    try:
        return getattr(p, attr, default) if p else default
    except Exception:
        return default


class UserBriefSerializer(serializers.ModelSerializer):
    apartment_no = serializers.SerializerMethodField()
    entrance_no = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()

    class Meta:
        model = SimpleUser
        fields = ("id", "login", "name", "has_parking", "is_active", "apartment_no", "entrance_no", "phone")

    def get_apartment_no(self, u):
        return _profile(u, "apartment_no", "")

    def get_entrance_no(self, u):
        return _profile(u, "entrance_no")

    def get_phone(self, u):
        return _profile(u, "phone", "")


class InvoiceSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    display_status = serializers.CharField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    is_blocking = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = (
            "id", "number", "title", "description", "period", "amount", "currency",
            "due_date", "block_on_overdue", "status", "display_status",
            "is_overdue", "is_blocking", "paid_at", "cancelled_at", "created_at",
        )
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    invoice_title = serializers.CharField(source="invoice.title", read_only=True)
    user = UserBriefSerializer(source="invoice.user", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id", "invoice", "invoice_number", "invoice_title", "user", "amount",
            "method", "provider", "status", "note", "recorded_by_name",
            "created_at", "completed_at",
        )

    def get_recorded_by_name(self, p):
        u = p.recorded_by
        return (u.name or u.login) if u else ""


class AdminInvoiceSerializer(InvoiceSerializer):
    user = UserBriefSerializer(read_only=True)
    created_by_name = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()

    class Meta(InvoiceSerializer.Meta):
        fields = InvoiceSerializer.Meta.fields + ("user", "batch", "created_by_name", "payments", "updated_at")
        read_only_fields = fields

    def get_created_by_name(self, inv):
        u = inv.created_by
        return (u.name or u.login) if u else ""

    def get_payments(self, inv):
        if not self.context.get("with_payments"):
            return None
        return PaymentSerializer(inv.payments.all(), many=True).data


class InvoiceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ("title", "description", "period", "amount", "due_date", "block_on_overdue")

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("Сумма должна быть больше нуля")
        return v

    def validate(self, attrs):
        inv = self.instance
        if inv and not inv.is_open:
            changed = {k for k in attrs if getattr(inv, k) != attrs[k]}
            if changed - {"description"}:
                raise serializers.ValidationError("Оплаченный или отменённый счёт менять нельзя")
        return attrs


class InvoiceCreateSerializer(serializers.Serializer):
    RECIPIENTS = (("users", "Выбранные жители"), ("parking", "Все с паркингом"), ("all", "Все жители"))

    recipients = serializers.ChoiceField(choices=RECIPIENTS)
    user_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    period = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    due_date = serializers.DateField()
    block_on_overdue = serializers.BooleanField(default=False)
    skip_duplicates = serializers.BooleanField(default=True)

    def validate_due_date(self, v):
        if v < today():
            raise serializers.ValidationError("Срок оплаты не может быть в прошлом")
        return v

    def validate(self, attrs):
        if attrs["recipients"] == "users" and not attrs.get("user_ids"):
            raise serializers.ValidationError({"user_ids": "Выберите хотя бы одного жителя"})
        return attrs


class MarkPaidSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=[Payment.METHOD_CASH, Payment.METHOD_TRANSFER])
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ResidentRowSerializer(UserBriefSerializer):
    role = serializers.CharField(read_only=True)
    approval_status = serializers.SerializerMethodField()
    car_number = serializers.SerializerMethodField()
    open_count = serializers.IntegerField(read_only=True, default=0)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=0)
    blocked = serializers.BooleanField(read_only=True, default=False)
    is_service = serializers.BooleanField(read_only=True, default=False)
    overdue = serializers.BooleanField(read_only=True, default=False)

    class Meta(UserBriefSerializer.Meta):
        fields = UserBriefSerializer.Meta.fields + (
            "role", "approval_status", "car_number", "open_count", "outstanding", "blocked", "is_service", "overdue", "created_at",
        )

    def get_approval_status(self, u):
        return _profile(u, "approval_status", "")

    def get_car_number(self, u):
        return _profile(u, "car_number", "")


class ResidentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SimpleUser
        fields = ("has_parking", "is_active")
