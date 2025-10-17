from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    LoginView, LogoutView, RefreshView, MeView,
    ApartmentViewSet, HouseList, EntranceList,
    DeviceByEntranceView, DeviceGlobalView,
    ProfileMeView, PasswordStatusView, ChangePasswordView,
    ApprovalStatusView,   # <--- добавим вьюху (см. ниже)
)

router = DefaultRouter()
router.register(r"apartments", ApartmentViewSet, basename="apartments")

urlpatterns = [
    path("admin/", admin.site.urls),

    # auth
    path("api/auth/login/",   LoginView.as_view()),
    path("api/auth/logout/",  LogoutView.as_view()),
    path("api/auth/refresh/", RefreshView.as_view()),   # <--- со слешем
    path("api/auth/me/",      MeView.as_view()),
    path("api/profile/me/",        ProfileMeView.as_view()),
    path("api/me/approval-status/", ApprovalStatusView.as_view()),  # <--- НОВОЕ
    path("api/me/password-status/",  PasswordStatusView.as_view()),
    path("api/me/change-password/",  ChangePasswordView.as_view()),
    # data
    path("api/", include(router.urls)),
    path("api/houses/", HouseList.as_view()),
    path("api/entrances/", EntranceList.as_view()),
    # подъезд и лифты (1..8)
    path("api/entrances/<int:no>/<slug:kind>/", DeviceByEntranceView.as_view()),
    path("api/<slug:kind>/", DeviceGlobalView.as_view()),
]
