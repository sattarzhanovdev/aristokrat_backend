from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from api.views import (
    LoginView,
    ApartmentViewSet,
    HouseList,
    EntranceList,
    DeviceByEntranceView,
    DeviceGlobalView,
)

router = DefaultRouter()
router.register(r"apartments", ApartmentViewSet, basename="apartments")

urlpatterns = [
    path("admin/", admin.site.urls),

    # auth (простая, без токенов)
    path("api/auth/login/", LoginView.as_view()),

    # data
    path("api/", include(router.urls)),
    path("api/houses/", HouseList.as_view()),
    path("api/entrances/", EntranceList.as_view()),

    # devices
    path("api/entrances/<int:no>/<slug:kind>/", DeviceByEntranceView.as_view()),
    path("api/<slug:kind>/", DeviceGlobalView.as_view()),
]
