"""
Платёжные провайдеры.

Чтобы подключить реальную платёжную систему (Freedom Pay, Mbank, O!Деньги,
Kaspi и т.п.), достаточно написать класс-наследник BaseProvider с двумя
методами и указать его код в settings.BILLING_PROVIDER:

    create_checkout(payment, request) -> CheckoutResult
        Создать платёж у провайдера и вернуть ссылку на страницу оплаты.

    parse_webhook(request) -> WebhookResult
        Разобрать уведомление провайдера (проверив подпись!) и сказать,
        какой это платёж и прошёл ли он.

Всё остальное (закрытие счёта, снятие блокировки, идемпотентность)
делает общий код в views.py.
"""
from dataclasses import dataclass, field

from django.conf import settings


@dataclass
class CheckoutResult:
    url: str
    provider_payment_id: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class WebhookResult:
    payment_id: int | None = None
    provider_payment_id: str = ""
    succeeded: bool = False
    failed: bool = False
    raw: dict = field(default_factory=dict)
    # что вернуть провайдеру в ответ (у многих свой формат)
    response_body: str = "OK"
    response_content_type: str = "text/plain"


class BaseProvider:
    code = ""
    title = ""

    def create_checkout(self, payment, request) -> CheckoutResult:  # pragma: no cover
        raise NotImplementedError

    def parse_webhook(self, request) -> WebhookResult:  # pragma: no cover
        raise NotImplementedError


def _registry():
    from .demo import DemoProvider

    return {p.code: p for p in (DemoProvider,)}


def get_provider():
    """Активный провайдер или None, если онлайн-оплата выключена."""
    code = (getattr(settings, "BILLING_PROVIDER", "") or "").strip()
    if not code:
        return None
    cls = _registry().get(code)
    return cls() if cls else None
