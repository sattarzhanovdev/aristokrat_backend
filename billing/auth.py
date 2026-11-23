"""
Токен для API.

Раньше бэкенд не выдавал токенов: приложение хранило логин/пароль и
периодически логинилось заново. Для счетов и админки нужен способ
понять, КТО делает запрос, поэтому логин теперь дополнительно отдаёт
подписанный токен (django.core.signing, без новых зависимостей).

Токен перестаёт работать, если пароль сменили или аккаунт выключили.
"""
import hashlib

from django.core import signing
from rest_framework import authentication, exceptions, permissions

from api.models import SimpleUser

SALT = "aristokrat.api.token"
MAX_AGE = 60 * 60 * 24 * 60  # 60 дней; приложение и так перелогинивается раз в 5 минут


def _pw_fingerprint(user):
    return hashlib.sha256(f"{user.pk}:{user.password}".encode()).hexdigest()[:16]


def issue_token(user):
    return signing.dumps({"u": user.pk, "p": _pw_fingerprint(user)}, salt=SALT, compress=True)


def user_from_token(token):
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return None
    user = SimpleUser.objects.filter(pk=data.get("u"), is_active=True).select_related("profile").first()
    if not user or data.get("p") != _pw_fingerprint(user):
        return None
    return user


class TokenAuth(authentication.BaseAuthentication):
    """Authorization: Bearer <token>"""

    keyword = "bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8", "ignore").split()
        if not header or header[0].lower() != self.keyword:
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("Неверный заголовок авторизации")
        user = user_from_token(header[1])
        if not user:
            raise exceptions.AuthenticationFailed("Сессия истекла. Войдите снова.")
        # DRF ожидает is_authenticated у пользователя
        user.is_authenticated = True
        return (user, None)

    def authenticate_header(self, request):
        return "Bearer"


class IsSignedIn(permissions.BasePermission):
    message = "Нужно войти в аккаунт"

    def has_permission(self, request, view):
        return isinstance(request.user, SimpleUser)


class IsAdminRole(permissions.BasePermission):
    message = "Только для администратора"

    def has_permission(self, request, view):
        return isinstance(request.user, SimpleUser) and request.user.role == "admin"
