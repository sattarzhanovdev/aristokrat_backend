from django.urls import path

from . import views

urlpatterns = [
    # житель
    path("api/billing/me/", views.MyBillingView.as_view()),
    path("api/billing/invoices/<int:pk>/pay/", views.PayInvoiceView.as_view()),
    path("api/billing/payments/<int:pk>/", views.MyPaymentView.as_view()),
    # платёжные системы
    path("api/billing/webhook/<slug:code>/", views.provider_webhook, name="billing-webhook"),
    path("api/billing/demo/<str:token>/", views.demo_checkout, name="billing-demo-checkout"),
    # админ-панель
    path("api/admin/overview/", views.AdminOverviewView.as_view()),
    path("api/admin/invoices/", views.AdminInvoicesView.as_view()),
    path("api/admin/invoices/<int:pk>/", views.AdminInvoiceDetailView.as_view()),
    path("api/admin/invoices/<int:pk>/cancel/", views.AdminInvoiceCancelView.as_view()),
    path("api/admin/invoices/<int:pk>/mark-paid/", views.AdminInvoiceMarkPaidView.as_view()),
    path("api/admin/batches/", views.AdminBatchesView.as_view()),
    path("api/admin/batches/<slug:batch>/", views.AdminBatchDetailView.as_view()),
    path("api/admin/batches/<slug:batch>/cancel/", views.AdminBatchCancelView.as_view()),
    path("api/admin/residents/", views.AdminResidentsView.as_view()),
    path("api/admin/residents/<int:pk>/", views.AdminResidentDetailView.as_view()),
    path("api/admin/payments/", views.AdminPaymentsView.as_view()),
    path("api/admin/test-payments/", views.AdminTestPaymentsView.as_view()),
    path("api/admin/settings/", views.AdminSettingsView.as_view()),
]
