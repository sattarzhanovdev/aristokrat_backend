import uuid
from datetime import timedelta
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.db import transaction
from django.db.models import Count, DecimalField, Exists, OuterRef, Q, Subquery, Sum, Value
from django.db.models import Case, IntegerField, Max, Min, When
from django.db.models.functions import Cast, Coalesce, TruncMonth
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import SimpleUser
from .auth import IsAdminRole, IsSignedIn, TokenAuth
from .models import BillingState, Invoice, Payment, today
from .providers import get_provider
from .providers.demo import unsign_payment
from .serializers import (
    AdminInvoiceSerializer, InvoiceCreateSerializer, InvoiceSerializer, InvoiceUpdateSerializer,
    MarkPaidSerializer, PaymentSerializer, ResidentRowSerializer, ResidentUpdateSerializer,
)


class Page(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class Authed(APIView):
    authentication_classes = [TokenAuth]
    permission_classes = [IsSignedIn]


class AdminView(APIView):
    authentication_classes = [TokenAuth]
    permission_classes = [IsAdminRole]

    def paginate(self, qs, serializer_cls, **ctx):
        p = Page()
        page = p.paginate_queryset(qs, self.request, view=self)
        return p.get_paginated_response(serializer_cls(page, many=True, context=ctx).data)


def online_payment_info():
    provider = get_provider()
    return {"enabled": bool(provider), "title": provider.title if provider else ""}


def _safe_return_url(url):
    """Разрешаем возвращаться только на наши фронтенды."""
    allowed = list(getattr(settings, "CORS_ALLOWED_ORIGINS", [])) + list(
        getattr(settings, "BILLING_EXTRA_RETURN_ORIGINS", [])
    )
    if url:
        u = urlparse(url)
        origin = f"{u.scheme}://{u.netloc}"
        if origin in allowed:
            return url
    return settings.BILLING_RETURN_URL


def _with_params(url, **params):
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urlencode(params)}"


# =====================================================================
#  ЖИТЕЛЬ
# =====================================================================

class MyBillingView(Authed):
    """Всё, что нужно экрану «Счета» и экрану блокировки."""

    def get(self, request):
        user = request.user
        base = Invoice.objects.filter(user=user)
        open_list = sorted(
            base.filter(status=Invoice.STATUS_ISSUED),
            key=lambda i: (not i.is_blocking, not i.is_overdue, i.due_date, i.pk),
        )
        history = base.exclude(status=Invoice.STATUS_ISSUED).order_by("-updated_at")[:30]
        return Response({
            "state": BillingState(user).as_dict(),
            "open": InvoiceSerializer(open_list, many=True).data,
            "history": InvoiceSerializer(history, many=True).data,
            "online_payment": online_payment_info(),
            "support_phone": settings.BILLING_SUPPORT_PHONE,
        })


class PayInvoiceView(Authed):
    """Создаёт онлайн-платёж и возвращает ссылку на страницу оплаты."""

    def post(self, request, pk):
        provider = get_provider()
        if not provider:
            return Response(
                {"message": "Онлайн-оплата пока не подключена. Оплатите администратору."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            inv = get_object_or_404(Invoice.objects.select_for_update(), pk=pk, user=request.user)
            if not inv.is_open:
                return Response({"message": "Этот счёт уже закрыт"}, status=status.HTTP_409_CONFLICT)
            # двойное нажатие / вернулся со страницы оплаты и нажал снова:
            # отдаём ту же незавершённую оплату, а не создаём вторую
            fresh = timezone.now() - timedelta(minutes=settings.BILLING_PENDING_REUSE_MINUTES)
            pending = (
                inv.payments.filter(status=Payment.STATUS_PENDING, provider=provider.code, created_at__gte=fresh)
                .exclude(checkout_url="").order_by("-created_at").first()
            )
            if pending:
                return Response({"payment_id": pending.pk, "checkout_url": pending.checkout_url})
            payment = Payment.objects.create(
                invoice=inv,
                amount=inv.amount,
                method=Payment.METHOD_ONLINE,
                provider=provider.code,
                return_url=_safe_return_url(request.data.get("return_url")),
            )
        try:
            result = provider.create_checkout(payment, request)
        except Exception as e:  # провайдер недоступен — не оставляем «висящий» платёж
            payment.fail({"error": str(e)})
            return Response(
                {"message": "Платёжная система не отвечает. Попробуйте позже."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        payment.checkout_url = result.url
        payment.provider_payment_id = result.provider_payment_id
        payment.raw = result.raw or {}
        payment.save(update_fields=["checkout_url", "provider_payment_id", "raw"])
        return Response({"payment_id": payment.pk, "checkout_url": result.url}, status=status.HTTP_201_CREATED)


class MyPaymentView(Authed):
    """Статус платежа — приложение опрашивает его после возврата со страницы оплаты."""

    def get(self, request, pk):
        p = get_object_or_404(Payment.objects.select_related("invoice"), pk=pk, invoice__user=request.user)
        return Response({
            "id": p.pk,
            "status": p.status,
            "invoice": InvoiceSerializer(p.invoice).data,
            "state": BillingState(request.user).as_dict(),
        })


@csrf_exempt
def provider_webhook(request, code):
    provider = get_provider()
    if request.method != "POST" or not provider or provider.code != code:
        raise Http404
    try:
        res = provider.parse_webhook(request)
    except Exception:
        return HttpResponse("bad request", status=400)

    qs = Payment.objects.select_related("invoice")
    payment = None
    if res.payment_id:
        payment = qs.filter(pk=res.payment_id, provider=code).first()
    if not payment and res.provider_payment_id:
        payment = qs.filter(provider_payment_id=res.provider_payment_id, provider=code).first()
    if not payment:
        return HttpResponse("unknown payment", status=404)

    with transaction.atomic():
        if res.succeeded:
            payment.succeed(res.raw)
        elif res.failed:
            payment.fail(res.raw)
    return HttpResponse(res.response_body, content_type=res.response_content_type)


@csrf_exempt
def demo_checkout(request, token):
    """Тестовая страница оплаты (только для BILLING_PROVIDER = 'demo')."""
    provider = get_provider()
    if not provider or provider.code != "demo":
        raise Http404
    pk = unsign_payment(token)
    payment = get_object_or_404(Payment.objects.select_related("invoice", "invoice__user"), pk=pk)

    if request.method == "POST" and payment.status == Payment.STATUS_PENDING:
        if request.POST.get("action") == "pay":
            payment.succeed({"demo": True})
        else:
            payment.fail({"demo": True, "cancelled": True})

    if payment.status != Payment.STATUS_PENDING:
        back = payment.return_url or settings.BILLING_RETURN_URL
        return HttpResponseRedirect(_with_params(back, payment=payment.pk, result=payment.status))

    inv = payment.invoice
    return render(request, "billing/demo_checkout.html", {
        "payment": payment, "invoice": inv, "currency": settings.BILLING_CURRENCY_LABEL,
    })


# =====================================================================
#  АДМИН
# =====================================================================

def _residents_qs():
    blocking = Invoice.objects.filter(Invoice.blocking_q(), user=OuterRef("pk"))
    overdue = Invoice.objects.filter(user=OuterRef("pk"), status=Invoice.STATUS_ISSUED, due_date__lt=today())
    open_sum = (
        Invoice.objects.filter(user=OuterRef("pk"), status=Invoice.STATUS_ISSUED)
        .values("user").annotate(s=Sum("amount")).values("s")
    )
    open_cnt = (
        Invoice.objects.filter(user=OuterRef("pk"), status=Invoice.STATUS_ISSUED)
        .values("user").annotate(c=Count("pk")).values("c")
    )
    money = DecimalField(max_digits=12, decimal_places=2)
    return (
        SimpleUser.objects.filter(role="resident")
        .select_related("profile")
        .annotate(
            is_service=Case(
                When(profile__apartment_no__in=settings.BILLING_SERVICE_APARTMENTS, then=Value(True)),
                default=Value(False),
            ),
            # номер квартиры числом, чтобы 2 шла раньше 10
            apt_num=Case(
                When(profile__apartment_no__regex=r"^[0-9]+$", then=Cast("profile__apartment_no", IntegerField())),
                default=Value(10**9),
                output_field=IntegerField(),
            ),
            blocked=Exists(blocking),
            overdue=Exists(overdue),
            outstanding=Coalesce(Subquery(open_sum, output_field=money), Value(0, output_field=money)),
            open_count=Coalesce(Subquery(open_cnt), Value(0)),
        )
    )


def _billable(qs):
    """Кому идут массовые счета: активные жители без служебных аккаунтов."""
    return qs.filter(is_active=True).exclude(profile__apartment_no__in=settings.BILLING_SERVICE_APARTMENTS)


def _search_users(qs, q, prefix=""):
    if not q:
        return qs
    f = Q(**{f"{prefix}name__icontains": q}) | Q(**{f"{prefix}login__icontains": q})
    f |= Q(**{f"{prefix}profile__apartment_no__iexact": q}) | Q(**{f"{prefix}profile__phone__icontains": q})
    f |= Q(**{f"{prefix}profile__car_number__icontains": q})
    return qs.filter(f)


class AdminOverviewView(AdminView):
    def get(self, request):
        now = timezone.localtime()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        open_qs = Invoice.objects.filter(status=Invoice.STATUS_ISSUED)
        ok_payments = Payment.objects.filter(status=Payment.STATUS_SUCCEEDED)

        six_months_ago = (month_start - timedelta(days=150)).replace(day=1)
        monthly = (
            ok_payments.filter(completed_at__gte=six_months_ago)
            .annotate(m=TruncMonth("completed_at")).values("m")
            .annotate(total=Sum("amount"), count=Count("pk")).order_by("m")
        )
        by_month = {row["m"].date().replace(day=1): row for row in monthly}
        months = []
        cursor = six_months_ago.date()
        for _ in range(6):
            row = by_month.get(cursor)
            months.append({
                "month": cursor.isoformat(),
                "total": str(row["total"]) if row else "0",
                "count": row["count"] if row else 0,
            })
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

        residents = _residents_qs()
        soon = today() + timedelta(days=7)
        return Response({
            "currency": settings.BILLING_CURRENCY,
            "outstanding": str(open_qs.aggregate(s=Sum("amount"))["s"] or 0),
            "open_count": open_qs.count(),
            "overdue_count": open_qs.filter(due_date__lt=today()).count(),
            "collected_month": str(ok_payments.filter(completed_at__gte=month_start).aggregate(s=Sum("amount"))["s"] or 0),
            "paid_month_count": ok_payments.filter(completed_at__gte=month_start).count(),
            "blocked_residents": residents.filter(blocked=True).count(),
            "debtors": residents.filter(overdue=True).count(),
            "residents_total": _billable(residents).count(),
            "parking_total": _billable(residents).filter(has_parking=True).count(),
            "approved_total": _billable(residents).filter(profile__approval_status="accepted").count(),
            "months": months,
            "due_soon": AdminInvoiceSerializer(
                open_qs.filter(due_date__gte=today(), due_date__lte=soon)
                .select_related("user", "user__profile").order_by("due_date")[:6], many=True,
            ).data,
            "recent_payments": PaymentSerializer(
                ok_payments.select_related("invoice", "invoice__user", "invoice__user__profile", "recorded_by")
                .order_by("-completed_at")[:6], many=True,
            ).data,
            "online_payment": online_payment_info(),
        })


class AdminInvoicesView(AdminView):
    def get(self, request):
        qs = Invoice.objects.select_related("user", "user__profile", "created_by")
        st = request.query_params.get("status", "all")
        d = today()
        if st == "open":
            qs = qs.filter(status=Invoice.STATUS_ISSUED, due_date__gte=d)
        elif st == "overdue":
            qs = qs.filter(status=Invoice.STATUS_ISSUED, due_date__lt=d)
        elif st == "blocking":
            qs = qs.filter(Invoice.blocking_q())
        elif st == "unpaid":
            qs = qs.filter(status=Invoice.STATUS_ISSUED)
        elif st in (Invoice.STATUS_PAID, Invoice.STATUS_CANCELLED):
            qs = qs.filter(status=st)
        if request.query_params.get("user"):
            qs = qs.filter(user_id=request.query_params["user"])
        if request.query_params.get("batch"):
            qs = qs.filter(batch=request.query_params["batch"])
        q = (request.query_params.get("q") or "").strip()
        if q:
            num = q.upper().removeprefix("A-").lstrip("0")
            by_user = _search_users(Invoice.objects.all(), q, prefix="user__").values("pk")
            f = Q(pk__in=by_user) | Q(title__icontains=q) | Q(period__icontains=q)
            if num.isdigit():
                f |= Q(pk=int(num))
            qs = qs.filter(f)
        order = {"due": ("due_date", "-pk"), "-amount": ("-amount", "-pk")}.get(
            request.query_params.get("ordering"), ("-created_at", "-pk"))
        return self.paginate(qs.order_by(*order), AdminInvoiceSerializer)

    def post(self, request):
        s = InvoiceCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        users = SimpleUser.objects.filter(role="resident", is_active=True)
        if v["recipients"] == "users":
            users = users.filter(pk__in=v["user_ids"])  # выбранных вручную — как есть, даже служебных
        elif v["recipients"] == "parking":
            users = _billable(users).filter(has_parking=True)
        else:
            users = _billable(users).filter(profile__approval_status="accepted")
        user_ids = list(users.values_list("pk", flat=True))
        if not user_ids:
            raise ValidationError({"message": "Нет жителей, которым можно выставить счёт"})

        skipped = 0
        if v["skip_duplicates"] and v["period"]:
            dup = set(
                Invoice.objects.filter(user_id__in=user_ids, title=v["title"], period=v["period"])
                .exclude(status=Invoice.STATUS_CANCELLED).values_list("user_id", flat=True)
            )
            skipped = len(dup)
            user_ids = [u for u in user_ids if u not in dup]

        # у каждого выставления свой id — по нему счета видны одной группой
        batch = uuid.uuid4().hex[:12]
        objs = [
            Invoice(
                user_id=uid, title=v["title"], description=v["description"], period=v["period"],
                amount=v["amount"], currency=settings.BILLING_CURRENCY, due_date=v["due_date"],
                block_on_overdue=v["block_on_overdue"], batch=batch, created_by=request.user,
            )
            for uid in user_ids
        ]
        with transaction.atomic():
            Invoice.objects.bulk_create(objs, batch_size=200)
        return Response({"created": len(objs), "skipped": skipped, "batch": batch}, status=status.HTTP_201_CREATED)


def _batch_rows(qs):
    """Выставления: счета одной рассылки, свёрнутые в строку с итогами."""
    d = today()
    issued = Q(status=Invoice.STATUS_ISSUED)
    money = DecimalField(max_digits=14, decimal_places=2)
    zero = Value(0, output_field=money)
    return (
        qs.exclude(batch="").values("batch")
        .annotate(
            # имена не совпадают с полями модели, иначе Django путает их в агрегатах
            b_title=Max("title"), b_period=Max("period"), b_amount=Max("amount"), b_currency=Max("currency"),
            b_due=Max("due_date"), b_block=Max("block_on_overdue"),
            b_created=Min("created_at"), b_author=Max("created_by__name"),
            total=Count("pk"),
            paid=Count("pk", filter=Q(status=Invoice.STATUS_PAID)),
            cancelled=Count("pk", filter=Q(status=Invoice.STATUS_CANCELLED)),
            open=Count("pk", filter=issued),
            overdue=Count("pk", filter=issued & Q(due_date__lt=d)),
            blocking=Count("pk", filter=issued & Q(due_date__lt=d, block_on_overdue=True)),
            sum_total=Coalesce(Sum("amount", filter=~Q(status=Invoice.STATUS_CANCELLED)), zero),
            sum_paid=Coalesce(Sum("amount", filter=Q(status=Invoice.STATUS_PAID)), zero),
        )
        .order_by("-b_created")
    )


def _batch_json(r):
    return {
        "batch": r["batch"], "title": r["b_title"], "period": r["b_period"],
        "amount": str(r["b_amount"]), "currency": r["b_currency"],
        "due_date": r["b_due"].isoformat() if r["b_due"] else None,
        "block_on_overdue": bool(r["b_block"]),
        "created_at": r["b_created"].isoformat() if r["b_created"] else None,
        "created_by": r["b_author"] or "",
        "total": r["total"], "paid": r["paid"], "cancelled": r["cancelled"], "open": r["open"],
        "overdue": r["overdue"], "blocking": r["blocking"],
        "sum_total": str(r["sum_total"]), "sum_paid": str(r["sum_paid"]),
    }


class AdminBatchesView(AdminView):
    """Список выставлений («Паркинг · Декабрь — 58 счетов, оплачено 30»)."""

    def get(self, request):
        qs = Invoice.objects.all()
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(period__icontains=q))
        rows = _batch_rows(qs)
        st = request.query_params.get("status")
        if st == "active":
            rows = rows.filter(open__gt=0)
        elif st == "done":
            rows = rows.filter(open=0)
        p = Page()
        page = p.paginate_queryset(rows, request, view=self)
        return p.get_paginated_response([_batch_json(r) for r in page])


def _deletable(qs):
    """Какие счета можно удалить, а какие нельзя и почему.

    Нельзя: оплаченные (пропадёт запись о полученных деньгах) и те, по которым
    житель прямо сейчас платит онлайн (деньги придут, а счёта уже не будет).
    """
    paying_since = timezone.now() - timedelta(hours=24)
    paying = Payment.objects.filter(status=Payment.STATUS_PENDING, created_at__gte=paying_since).values("invoice")
    has_money = Payment.objects.filter(status=Payment.STATUS_SUCCEEDED).values("invoice")
    paid = qs.filter(Q(status=Invoice.STATUS_PAID) | Q(pk__in=has_money))
    in_progress = qs.exclude(pk__in=paid.values("pk")).filter(pk__in=paying)
    ok = qs.exclude(pk__in=paid.values("pk")).exclude(pk__in=in_progress.values("pk"))
    return ok, paid.count(), in_progress.count()


class AdminBatchDetailView(AdminView):
    def delete(self, request, batch):
        """Удалить выставление: неоплаченные и отменённые счета удаляются,
        оплаченные остаются (как история денег)."""
        qs = Invoice.objects.filter(batch=batch)
        if not qs.exists():
            raise Http404
        ok, kept_paid, kept_paying = _deletable(qs)
        with transaction.atomic():
            deleted = ok.count()
            ok.delete()  # незавершённые платежи удаляются вместе со счётом
        return Response({
            "deleted": deleted, "kept_paid": kept_paid, "kept_paying": kept_paying,
            "remaining": Invoice.objects.filter(batch=batch).count(),
        })

    def _row(self, batch):
        row = _batch_rows(Invoice.objects.filter(batch=batch)).first()
        if not row:
            raise Http404
        return Response(_batch_json(row))

    def get(self, request, batch):
        return self._row(batch)

    def patch(self, request, batch):
        """Продлить срок всем неоплаченным счетам выставления."""
        s = InvoiceUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        due = s.validated_data.get("due_date")
        if not due or due < today():
            raise ValidationError({"due_date": "Укажите срок не раньше сегодняшнего дня"})
        Invoice.objects.filter(batch=batch, status=Invoice.STATUS_ISSUED).update(due_date=due, updated_at=timezone.now())
        return self._row(batch)


class AdminBatchCancelView(AdminView):
    """Отменить все неоплаченные счета выставления (оплаченные не трогаем)."""

    def post(self, request, batch):
        n = 0
        for inv in Invoice.objects.filter(batch=batch, status=Invoice.STATUS_ISSUED):
            if inv.cancel():
                inv.payments.filter(status=Payment.STATUS_PENDING).update(
                    status=Payment.STATUS_FAILED, completed_at=timezone.now())
                n += 1
        resp = AdminBatchDetailView()._row(batch)
        resp.data["cancelled_now"] = n
        return resp


def _invoice_detail(pk):
    inv = get_object_or_404(
        Invoice.objects.select_related("user", "user__profile", "created_by").prefetch_related("payments"), pk=pk
    )
    return Response(AdminInvoiceSerializer(inv, context={"with_payments": True}).data)


class AdminInvoiceDetailView(AdminView):
    def get(self, request, pk):
        return _invoice_detail(pk)

    def delete(self, request, pk):
        inv = get_object_or_404(Invoice, pk=pk)
        ok, paid, paying = _deletable(Invoice.objects.filter(pk=pk))
        if paid:
            return Response(
                {"message": "Оплаченный счёт удалить нельзя — это запись о полученных деньгах."},
                status=status.HTTP_409_CONFLICT,
            )
        if paying:
            return Response(
                {"message": "Житель сейчас оплачивает этот счёт. Попробуйте позже или отмените счёт."},
                status=status.HTTP_409_CONFLICT,
            )
        inv.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk):
        inv = get_object_or_404(Invoice, pk=pk)
        s = InvoiceUpdateSerializer(inv, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return _invoice_detail(pk)


class AdminInvoiceCancelView(AdminView):
    def post(self, request, pk):
        inv = get_object_or_404(Invoice, pk=pk)
        if not inv.cancel():
            return Response({"message": "Отменить можно только неоплаченный счёт"}, status=status.HTTP_409_CONFLICT)
        inv.payments.filter(status=Payment.STATUS_PENDING).update(status=Payment.STATUS_FAILED, completed_at=timezone.now())
        return _invoice_detail(pk)


class AdminInvoiceMarkPaidView(AdminView):
    def post(self, request, pk):
        s = MarkPaidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            inv = get_object_or_404(Invoice.objects.select_for_update(), pk=pk)
            if not inv.is_open:
                return Response({"message": "Счёт уже закрыт"}, status=status.HTTP_409_CONFLICT)
            p = Payment.objects.create(
                invoice=inv, amount=inv.amount, method=s.validated_data["method"],
                note=s.validated_data["note"], recorded_by=request.user,
            )
            p.succeed()
        return _invoice_detail(pk)


class AdminResidentsView(AdminView):
    def get(self, request):
        qs = _search_users(_residents_qs(), (request.query_params.get("q") or "").strip())
        f = request.query_params.get("filter", "all")
        if f == "blocked":
            qs = qs.filter(blocked=True)
        elif f == "debtors":
            qs = qs.filter(overdue=True)
        elif f == "unpaid":
            qs = qs.filter(open_count__gt=0)
        elif f == "parking":
            qs = qs.filter(has_parking=True)
        elif f == "inactive":
            qs = qs.filter(is_active=False)
        ordering = request.query_params.get("ordering")
        if ordering == "debt":
            qs = qs.order_by("-outstanding", "apt_num", "pk")
        else:
            # по номеру квартиры; служебные (10000) и нечисловые — в конце
            qs = qs.order_by("is_service", "apt_num", "pk")
        return self.paginate(qs, ResidentRowSerializer)


class AdminResidentDetailView(AdminView):
    def _payload(self, pk):
        u = get_object_or_404(_residents_qs(), pk=pk)
        invoices = Invoice.objects.filter(user=u).select_related("created_by").order_by("-created_at")[:100]
        return {
            "resident": ResidentRowSerializer(u).data,
            "state": BillingState(u).as_dict(),
            "invoices": AdminInvoiceSerializer(invoices, many=True).data,
        }

    def get(self, request, pk):
        return Response(self._payload(pk))

    def patch(self, request, pk):
        u = get_object_or_404(SimpleUser, pk=pk, role="resident")
        s = ResidentUpdateSerializer(u, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(self._payload(pk))


class AdminPaymentsView(AdminView):
    def get(self, request):
        Payment.expire_stale()
        qs = Payment.objects.select_related("invoice", "invoice__user", "invoice__user__profile", "recorded_by")
        st = request.query_params.get("status", "succeeded")
        if st in dict(Payment.STATUS_CHOICES):
            qs = qs.filter(status=st)
        m = request.query_params.get("method")
        if m in dict(Payment.METHOD_CHOICES):
            qs = qs.filter(method=m)
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(invoice__in=_search_users(Invoice.objects.all(), q, prefix="user__").values("pk"))
        return self.paginate(qs.order_by("-created_at"), PaymentSerializer)


class AdminTestPaymentsView(AdminView):
    """Тестовые оплаты (через демо-страницу, provider="demo").

    GET — сколько их; DELETE — удалить. Счета, которые были «оплачены» только
    тестовой оплатой, снова становятся неоплаченными (и снова могут блокировать).
    Настоящие оплаты и отметки «наличными/переводом» не трогаются.
    """

    def _stats(self):
        demo = Payment.objects.filter(provider="demo")
        return {
            "payments": demo.count(),
            "succeeded": demo.filter(status=Payment.STATUS_SUCCEEDED).count(),
            "invoices": demo.filter(status=Payment.STATUS_SUCCEEDED).values("invoice").distinct().count(),
        }

    def get(self, request):
        return Response(self._stats())

    def delete(self, request):
        with transaction.atomic():
            demo = Payment.objects.filter(provider="demo")
            touched = list(demo.filter(status=Payment.STATUS_SUCCEEDED).values_list("invoice", flat=True).distinct())
            deleted = demo.count()
            demo.delete()
            real_money = Payment.objects.filter(status=Payment.STATUS_SUCCEEDED).values("invoice")
            reopened = (
                Invoice.objects.filter(pk__in=touched, status=Invoice.STATUS_PAID)
                .exclude(pk__in=real_money)
                .update(status=Invoice.STATUS_ISSUED, paid_at=None, updated_at=timezone.now())
            )
        return Response({"deleted": deleted, "reopened": reopened, **self._stats()})


class AdminSettingsView(AdminView):
    def get(self, request):
        return Response({
            "currency": settings.BILLING_CURRENCY,
            "currency_label": settings.BILLING_CURRENCY_LABEL,
            "online_payment": online_payment_info(),
            "provider_code": getattr(settings, "BILLING_PROVIDER", ""),
            "return_url": settings.BILLING_RETURN_URL,
            "support_phone": settings.BILLING_SUPPORT_PHONE,
        })
