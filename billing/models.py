"""
Счета и оплаты.

Правило блокировки (одно место истины — Invoice.blocking_q / BillingState):
житель заблокирован, если у него есть счёт, который
  • не оплачен и не отменён (status = issued),
  • выставлен с галочкой «Блокировать при неуплате» (block_on_overdue = True),
  • и срок оплаты уже прошёл (due_date < сегодня).
Блокировка вычисляется на лету, поэтому после оплаты (или отмены/продления
счёта админом) доступ открывается сам, без отдельных флагов.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from api.models import SimpleUser


def today():
    return timezone.localdate()


class Invoice(models.Model):
    STATUS_ISSUED = "issued"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_ISSUED, "Ожидает оплаты"),
        (STATUS_PAID, "Оплачен"),
        (STATUS_CANCELLED, "Отменён"),
    ]

    user = models.ForeignKey(
        SimpleUser, on_delete=models.CASCADE, related_name="invoices", verbose_name="Житель"
    )
    title = models.CharField(max_length=160, verbose_name="Назначение")
    description = models.TextField(blank=True, verbose_name="Описание")
    period = models.CharField(max_length=40, blank=True, verbose_name="Период")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма")
    currency = models.CharField(max_length=8, default=settings.BILLING_CURRENCY, verbose_name="Валюта")

    due_date = models.DateField(verbose_name="Оплатить до")
    block_on_overdue = models.BooleanField(
        default=False, verbose_name="Блокировать при неуплате",
        help_text="Если срок прошёл, а счёт не оплачен — у жителя закрывается доступ к паркингу.",
    )

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ISSUED, db_index=True, verbose_name="Статус")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Оплачен")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="Отменён")

    batch = models.CharField(max_length=32, blank=True, db_index=True, verbose_name="Пакет",
                             help_text="Общий идентификатор счетов, выставленных одной рассылкой.")
    created_by = models.ForeignKey(
        SimpleUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Выставил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    class Meta:
        verbose_name = "Счёт"
        verbose_name_plural = "Счета"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "status", "due_date"])]

    def __str__(self):
        return f"{self.number} · {self.title} · {self.amount} {self.currency}"

    # ---------- вычисляемое ----------

    @property
    def number(self):
        return f"A-{self.pk:06d}" if self.pk else "A-новый"

    @property
    def is_open(self):
        return self.status == self.STATUS_ISSUED

    @property
    def is_overdue(self):
        return self.is_open and self.due_date < today()

    @property
    def is_blocking(self):
        return self.is_overdue and self.block_on_overdue

    @property
    def display_status(self):
        """issued | overdue | blocking | paid | cancelled — для интерфейса."""
        if self.is_blocking:
            return "blocking"
        if self.is_overdue:
            return "overdue"
        return self.status

    @staticmethod
    def blocking_q(prefix=""):
        """Q-фильтр «этот счёт сейчас блокирует жителя»."""
        return Q(**{
            f"{prefix}status": Invoice.STATUS_ISSUED,
            f"{prefix}block_on_overdue": True,
            f"{prefix}due_date__lt": today(),
        })

    # ---------- действия ----------

    def mark_paid(self, when=None):
        if self.status == self.STATUS_PAID:
            return False
        self.status = self.STATUS_PAID
        self.paid_at = when or timezone.now()
        self.save(update_fields=["status", "paid_at", "updated_at"])
        return True

    def cancel(self):
        if self.status != self.STATUS_ISSUED:
            return False
        self.status = self.STATUS_CANCELLED
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "cancelled_at", "updated_at"])
        return True


class Payment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "В процессе"),
        (STATUS_SUCCEEDED, "Успешно"),
        (STATUS_FAILED, "Не прошла"),
    ]

    METHOD_ONLINE = "online"
    METHOD_CASH = "cash"
    METHOD_TRANSFER = "transfer"
    METHOD_CHOICES = [
        (METHOD_ONLINE, "Онлайн"),
        (METHOD_CASH, "Наличные"),
        (METHOD_TRANSFER, "Перевод"),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments", verbose_name="Счёт")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма")
    method = models.CharField(max_length=16, choices=METHOD_CHOICES, default=METHOD_ONLINE, verbose_name="Способ")
    provider = models.CharField(max_length=32, blank=True, verbose_name="Платёжная система")
    provider_payment_id = models.CharField(max_length=128, blank=True, db_index=True, verbose_name="ID у провайдера")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True, verbose_name="Статус")
    checkout_url = models.URLField(max_length=600, blank=True)
    return_url = models.URLField(max_length=600, blank=True)
    raw = models.JSONField(default=dict, blank=True, verbose_name="Ответ провайдера")
    note = models.CharField(max_length=255, blank=True, verbose_name="Комментарий")
    recorded_by = models.ForeignKey(
        SimpleUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Отметил вручную",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершён")

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Платёж #{self.pk} · {self.invoice.number} · {self.get_status_display()}"

    def succeed(self, raw=None):
        """Зачисляет платёж и закрывает счёт. Повторный вызов безопасен."""
        if self.status == self.STATUS_SUCCEEDED:
            return False
        already_paid = self.invoice.payments.filter(status=self.STATUS_SUCCEEDED).exclude(pk=self.pk).exists()
        self.status = self.STATUS_SUCCEEDED
        self.completed_at = timezone.now()
        if raw:
            self.raw = raw
        if already_paid:
            # деньги пришли второй раз (онлайн + наличные, две вкладки и т.п.)
            self.note = "Повторная оплата — нужен возврат"
        self.save(update_fields=["status", "completed_at", "raw", "note"])
        self.invoice.mark_paid(self.completed_at)
        return True

    @classmethod
    def expire_stale(cls, hours=24):
        """Брошенные попытки оплаты не висят «в процессе» вечно.
        Если провайдер всё же подтвердит такую оплату позже, succeed() её примет."""
        cutoff = timezone.now() - timedelta(hours=hours)
        return cls.objects.filter(status=cls.STATUS_PENDING, created_at__lt=cutoff).update(
            status=cls.STATUS_FAILED, completed_at=timezone.now(), note="Не завершена — истекла"
        )

    def fail(self, raw=None):
        if self.status != self.STATUS_PENDING:
            return False
        self.status = self.STATUS_FAILED
        self.completed_at = timezone.now()
        if raw:
            self.raw = raw
        self.save(update_fields=["status", "completed_at", "raw"])
        return True


class BillingState:
    """Сводка по счетам одного жителя — то, что видит приложение."""

    def __init__(self, user):
        open_qs = Invoice.objects.filter(user=user, status=Invoice.STATUS_ISSUED)
        self.blocking_count = open_qs.filter(Invoice.blocking_q()).count()
        self.blocked = self.blocking_count > 0 and user.role != "admin"
        self.open_count = open_qs.count()
        self.overdue_count = open_qs.filter(due_date__lt=today()).count()
        self.outstanding = open_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        nearest = open_qs.order_by("due_date").values_list("due_date", flat=True).first()
        self.next_due = nearest

    def as_dict(self):
        return {
            "blocked": self.blocked,
            "blocking_count": self.blocking_count,
            "open_count": self.open_count,
            "overdue_count": self.overdue_count,
            "outstanding": str(self.outstanding),
            "currency": settings.BILLING_CURRENCY,
            "next_due": self.next_due.isoformat() if self.next_due else None,
        }
