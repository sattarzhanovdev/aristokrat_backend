import re
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import generics, permissions, status, viewsets, mixins
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.hashers import check_password
from rest_framework.permissions import IsAdminUser

from .models import House, Entrance, Apartment, Device, ResidentProfile
from .serializers import (
    UserSerializer, HouseSerializer, EntranceSerializer,
    ApartmentSerializer, ApartmentListSerializer, ProfileMeSerializer
)

from django.contrib.auth import get_user_model

from rest_framework.permissions import IsAuthenticated
# ---- AUTH ----

try:
    from rest_framework_simplejwt.authentication import JWTAuthentication
    AUTHN = [JWTAuthentication]
except Exception:
    from rest_framework.authentication import SessionAuthentication
    AUTHN = [SessionAuthentication]


def set_refresh_cookie(response, refresh):
    # httpOnly cookie
    response.set_cookie(
        key="refresh",
        value=str(refresh),
        httponly=True,
        samesite="Lax",
        secure=False,         # True на проде
        max_age=14*24*3600,
        path="/api/auth/",
    )

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        login = request.data.get("login", "").strip()
        password = request.data.get("password", "")

        # определить username по email или взять как есть
        username = None
        if re.match(r"^\S+@\S+\.\S+$", login):
            try:
                username = User.objects.get(email__iexact=login).username
            except User.DoesNotExist:
                pass
        if username is None:
            username = login

        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({"message": "Неверный логин или пароль"}, status=400)

        # refresh_obj -- это уже refresh-токен
        refresh_obj = RefreshToken.for_user(user)
        access_token = str(refresh_obj.access_token)  # access из refresh
        refresh_token = str(refresh_obj)              # сам refresh как строка

        data = {
            "accessToken": access_token,
            "refreshToken": refresh_token,            # <-- вот он
            "user": UserSerializer(user).data,
        }

        resp = Response(data, status=200)
        # если хочешь хранить refresh в cookie (рекомендовано)
        set_refresh_cookie(resp, refresh_token)
        return resp
    
class RefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.COOKIES.get("refresh") or (request.data or {}).get("refreshToken")
        if not token:
            return Response({"message": "Нет refresh-токена"}, status=401)
        try:
            refresh = RefreshToken(token)
            access = str(refresh.access_token)
            return Response({"accessToken": access}, status=200)
        except Exception:
            return Response({"message": "Неверный refresh-токен"}, status=401)

class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        resp = Response(status=204)
        resp.delete_cookie("refresh", path="/api/auth/")
        return resp

class MeView(APIView):
    authentication_classes = AUTHN
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response(UserSerializer(request.user).data)

# ---- DATA ----

class ApartmentPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

class ApartmentViewSet(viewsets.ModelViewSet):
    queryset = Apartment.objects.select_related("entrance", "entrance__house").all()
    serializer_class = ApartmentSerializer
    pagination_class = ApartmentPagination

    @action(detail=True, methods=["patch"], url_path="accept", permission_classes=[IsAdminUser])
    def accept(self, request, pk=None):
        ap = self.get_object()
        house = ap.entrance.house.number
        entrance = ap.entrance.number
        number = ap.number

        updated = ResidentProfile.objects.filter(
            house_number=house,
            entrance_no=entrance,
            apartment_no=number
        ).update(approval_status="accepted")
        return Response({"updated_profiles": updated, "approval_status": "accepted"})

    @action(detail=True, methods=["patch"], url_path="reject", permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        ap = self.get_object()
        house = ap.entrance.house.number
        entrance = ap.entrance.number
        number = ap.number

        updated = ResidentProfile.objects.filter(
            house_number=house,
            entrance_no=entrance,
            apartment_no=number
        ).update(approval_status="not_accepted")
        return Response({"updated_profiles": updated, "approval_status": "not_accepted"})
    
    def get_permissions(self):
        if self.action in ["block", "partial_update", "create", "update", "destroy"]:
            return [permissions.IsAdminUser()]
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def get_serializer_class(self):
        return ApartmentListSerializer if self.action == "list" else ApartmentSerializer

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()

        house = request.query_params.get("house")   # число
        entrance = request.query_params.get("entrance")
        search = request.query_params.get("search")

        if house:
            qs = qs.filter(entrance__house__number=house)
        if entrance:
            qs = qs.filter(entrance__number=entrance)
        if search:
            qs = qs.filter(number__icontains=search)

        self.queryset = qs
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["patch"], url_path="block")
    def block(self, request, pk=None):
        ap = self.get_object()
        ap.is_blocked = True
        ap.save(update_fields=["is_blocked", "updated_at"])
        return Response({"id": ap.id, "is_blocked": ap.is_blocked})

# Дополнительно (если нужно): списки домов и подъездов
class HouseList(generics.ListAPIView):
    queryset = House.objects.all().order_by("number")
    serializer_class = HouseSerializer

class EntranceList(generics.ListAPIView):
    serializer_class = EntranceSerializer

    def get_queryset(self):
        house = self.request.query_params.get("house")
        qs = Entrance.objects.select_related("house")
        return qs.filter(house__number=house) if house else qs



# Разрешённые виды для эндпоинта с номером подъезда
ENTRANCE_KINDS = {"door", "lift_pass", "lift_gruz"}
# Глобальные устройства без номера подъезда
GLOBAL_KINDS = {"kalitka1", "kalitka2", "kalitka3", "kalitka4", "parking"}

MAX_ENTRANCES = 8  # <-- если изменится, поправь одно место

class DeviceByEntranceView(APIView):
    permission_classes = [permissions.AllowAny]  # если нужно — поменяй на IsAuthenticated

    def _get(self, kind, no):
        if kind not in ENTRANCE_KINDS or not (1 <= no <= MAX_ENTRANCES):
            return None
        obj, _ = Device.objects.get_or_create(kind=kind, entrance_no=no)
        return obj

    def get(self, request, no, kind):
        dev = self._get(kind, no)
        if not dev:
            return Response(False, status=status.HTTP_404_NOT_FOUND)
        return Response(dev.state)

    def post(self, request, no, kind):
        dev = self._get(kind, no)
        if not dev:
            return Response(False, status=status.HTTP_404_NOT_FOUND)
        if not isinstance(request.data, dict) or "state" not in request.data:
            return Response(False, status=status.HTTP_400_BAD_REQUEST)
        dev.state = bool(request.data["state"])
        dev.save(update_fields=["state", "updated_at"])
        return Response(dev.state)


class DeviceGlobalView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get(self, kind):
        if kind not in GLOBAL_KINDS:
            return None
        obj, _ = Device.objects.get_or_create(kind=kind, entrance_no=None)
        return obj

    def get(self, request, kind):
        dev = self._get(kind)
        if not dev:
            return Response(False, status=status.HTTP_404_NOT_FOUND)
        return Response(dev.state)

    def post(self, request, kind):
        dev = self._get(kind)
        if not dev:
            return Response(False, status=status.HTTP_404_NOT_FOUND)
        if not isinstance(request.data, dict) or "state" not in request.data:
            return Response(False, status=status.HTTP_400_BAD_REQUEST)
        dev.state = bool(request.data["state"])
        dev.save(update_fields=["state", "updated_at"])
        return Response(dev.state)
      
      
User = get_user_model()

class ProfileMeView(APIView):
    authentication_classes = AUTHN
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ser = ProfileMeSerializer(request.user)
        return Response(ser.data)

    def put(self, request):
        ser = ProfileMeSerializer(instance=request.user, data=request.data, partial=False)
        if ser.is_valid():
            ser.save()
            return Response(ser.data)
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        ser = ProfileMeSerializer(instance=request.user, data=request.data, partial=True)
        if ser.is_valid():
            ser.save()
            return Response(ser.data)
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
    

class PasswordStatusView(APIView):
    authentication_classes = AUTHN
    permission_classes = [IsAuthenticated]
    def get(self, request):
        try:
            status_str = request.user.resident.password_status
        except ResidentProfile.DoesNotExist:
            status_str = "updated"  # по умолчанию
        return Response({"status": status_str})

class ChangePasswordView(APIView):
    authentication_classes = AUTHN
    permission_classes = [IsAuthenticated]
    def post(self, request):
        old = request.data.get("old_password") or ""
        new = request.data.get("new_password") or ""
        user = request.user
        if not check_password(old, user.password):
            return Response({"detail": "Неверный текущий пароль"}, status=400)
        if len(new) < 8:
            return Response({"detail": "Пароль должен быть не короче 8 символов"}, status=400)

        user.set_password(new)
        user.save()
        update_session_auth_hash(request, user)  # не вылогинивать

        try:
            prof = user.resident
            prof.password_status = "updated"
            prof.save(update_fields=["password_status", "updated_at"])
        except ResidentProfile.DoesNotExist:
            pass

        return Response({"status": "updated"})
    
    


class ApprovalStatusView(APIView):
    authentication_classes = AUTHN
    permission_classes = [IsAuthenticated]
    def get(self, request):
        try:
            status_str = request.user.resident.approval_status
        except ResidentProfile.DoesNotExist:
            status_str = "accepted"
        return Response({"status": status_str})