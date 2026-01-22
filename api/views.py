from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics, viewsets
from rest_framework.pagination import PageNumberPagination

from .models import (
    SimpleUser, House, Entrance, Apartment, Device
)
from .serializers import (
    SimpleUserSerializer,
    HouseSerializer, EntranceSerializer,
    ApartmentSerializer, ApartmentListSerializer
)


# ---------- AUTH ----------

class LoginView(APIView):
    permission_classes = []

    def post(self, request):
        login = request.data.get("login")
        password = request.data.get("password")

        user = SimpleUser.objects.filter(
            login=login,
            password=password,
            is_active=True
        ).first()

        if not user:
            return Response({"message": "Неверный логин или пароль"}, status=401)

        return Response(SimpleUserSerializer(user).data)


# ---------- APARTMENTS ----------

class ApartmentPagination(PageNumberPagination):
    page_size = 50


class ApartmentViewSet(viewsets.ModelViewSet):
    queryset = Apartment.objects.select_related("entrance", "entrance__house")
    serializer_class = ApartmentSerializer
    pagination_class = ApartmentPagination

    def get_serializer_class(self):
        return ApartmentListSerializer if self.action == "list" else ApartmentSerializer


# ---------- LISTS ----------

class HouseList(generics.ListAPIView):
    queryset = House.objects.all().order_by("number")
    serializer_class = HouseSerializer


class EntranceList(generics.ListAPIView):
    serializer_class = EntranceSerializer

    def get_queryset(self):
        house = self.request.query_params.get("house")
        qs = Entrance.objects.select_related("house")
        return qs.filter(house__number=house) if house else qs


# ---------- DEVICES ----------

class DeviceByEntranceView(APIView):
    permission_classes = []

    def get(self, request, no, kind):
        dev, _ = Device.objects.get_or_create(kind=kind, entrance_no=no)
        return Response(dev.state)

    def post(self, request, no, kind):
        dev, _ = Device.objects.get_or_create(kind=kind, entrance_no=no)
        dev.state = bool(request.data.get("state"))
        dev.save()
        return Response(dev.state)


class DeviceGlobalView(APIView):
    permission_classes = []

    def get(self, request, kind):
        dev, _ = Device.objects.get_or_create(kind=kind, entrance_no=None)
        return Response(dev.state)

    def post(self, request, kind):
        dev, _ = Device.objects.get_or_create(kind=kind, entrance_no=None)
        dev.state = bool(request.data.get("state"))
        dev.save()
        return Response(dev.state)
