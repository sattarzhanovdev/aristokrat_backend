from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    LoginView, LogoutView, RefreshView, MeView,
    ApartmentViewSet, HouseList, EntranceList, DeviceByEntranceView, DeviceGlobalView, ProfileMeView
)

router = DefaultRouter()
router.register(r"apartments", ApartmentViewSet, basename="apartments")

urlpatterns = [
    path("admin/", admin.site.urls),

    # auth
    path("api/auth/login", LoginView.as_view()),
    path("api/auth/logout", LogoutView.as_view()),
    path("api/auth/refresh", RefreshView.as_view()),
    path("api/auth/me", MeView.as_view()),
    path("api/profile/me", ProfileMeView.as_view()),  # без слеша в конце или с — используй везде одинаково

    # data
    path("api/", include(router.urls)),
    path("api/houses", HouseList.as_view()),
    path("api/entrances", EntranceList.as_view()),
    # подъезд и лифты (1..8)
    path("api/entrances/<int:no>/<slug:kind>/", DeviceByEntranceView.as_view()),
    path("api/<slug:kind>/", DeviceGlobalView.as_view()),
]
