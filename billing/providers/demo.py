"""
Демо-провайдер: тестовая страница оплаты на нашем же сервере.

Нужен, чтобы проверить весь путь «счёт → оплата → разблокировка»
до подключения настоящей платёжной системы. Деньги не списываются.
На проде выключается: BILLING_PROVIDER = "" или код реального провайдера.
"""
from django.core import signing
from django.urls import reverse

from . import BaseProvider, CheckoutResult

SALT = "aristokrat.billing.demo"


def sign_payment(payment_id):
    return signing.dumps(payment_id, salt=SALT)


def unsign_payment(token):
    try:
        return int(signing.loads(token, salt=SALT, max_age=60 * 60 * 24))
    except (signing.BadSignature, ValueError, TypeError):
        return None


class DemoProvider(BaseProvider):
    code = "demo"
    title = "Тестовая оплата"

    def create_checkout(self, payment, request):
        token = sign_payment(payment.pk)
        url = request.build_absolute_uri(reverse("billing-demo-checkout", args=[token]))
        return CheckoutResult(url=url, provider_payment_id=f"demo-{payment.pk}")

    def parse_webhook(self, request):  # демо закрывает платёж прямо со своей страницы
        raise NotImplementedError
