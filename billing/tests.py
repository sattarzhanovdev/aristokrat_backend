from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import ResidentProfile, SimpleUser
from .auth import issue_token
from .models import Invoice, Payment, today
from .providers.demo import sign_payment


def make_user(login, role="resident", parking=True, **profile):
    u = SimpleUser.objects.create(login=login, password="pw", name=login.title(), role=role, has_parking=parking)
    ResidentProfile.objects.create(user=u, approval_status="accepted", **profile)
    return u


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_token(user)}")
    return c


@override_settings(BILLING_PROVIDER="demo")
class BillingFlowTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin", role="admin")
        self.r1 = make_user("r1", apartment_no="12")
        self.r2 = make_user("r2", apartment_no="13", parking=False)
        self.adm = client_for(self.admin)

    def login(self, user):
        return APIClient().post("/api/auth/login/", {"login": user.login, "password": "pw"}, format="json").json()

    def test_login_returns_token_and_billing(self):
        data = self.login(self.r1)
        self.assertIn("token", data)
        self.assertFalse(data["billing"]["blocked"])

    def test_admin_api_requires_admin(self):
        self.assertEqual(APIClient().get("/api/admin/overview/").status_code, 401)
        self.assertEqual(client_for(self.r1).get("/api/admin/overview/").status_code, 403)
        self.assertEqual(self.adm.get("/api/admin/overview/").status_code, 200)

    def test_token_dies_after_password_change(self):
        c = client_for(self.r1)
        self.r1.password = "new"
        self.r1.save()
        self.assertEqual(c.get("/api/billing/me/").status_code, 401)

    def test_bulk_invoices_for_parking_and_duplicates(self):
        body = {"recipients": "parking", "title": "Паркинг", "period": "Декабрь 2026", "amount": "1500",
                "due_date": (today() + timedelta(days=10)).isoformat(), "block_on_overdue": True}
        res = self.adm.post("/api/admin/invoices/", body, format="json").json()
        self.assertEqual(res["created"], 1)  # только r1 с паркингом, админ не в счёт
        res = self.adm.post("/api/admin/invoices/", body, format="json").json()
        self.assertEqual((res["created"], res["skipped"]), (0, 1))

    def test_overdue_with_flag_blocks_and_payment_unblocks(self):
        inv = Invoice.objects.create(user=self.r1, title="Паркинг", amount=Decimal("1500"),
                                     due_date=today() - timedelta(days=1), block_on_overdue=True)
        # без галочки просрочка не блокирует
        Invoice.objects.create(user=self.r2, title="Паркинг", amount=Decimal("1500"),
                               due_date=today() - timedelta(days=1), block_on_overdue=False)
        self.assertTrue(self.login(self.r1)["billing"]["blocked"])
        self.assertFalse(self.login(self.r2)["billing"]["blocked"])

        rows = self.adm.get("/api/admin/residents/?filter=blocked").json()["results"]
        self.assertEqual([r["id"] for r in rows], [self.r1.pk])

        # житель платит онлайн через демо-провайдер
        c = client_for(self.r1)
        pay = c.post(f"/api/billing/invoices/{inv.pk}/pay/",
                     {"return_url": "http://localhost:3000/bills"}, format="json").json()
        page = self.client.post(f"/api/billing/demo/{sign_payment(pay['payment_id'])}/", {"action": "pay"})
        self.assertEqual(page.status_code, 302)
        self.assertTrue(page["Location"].startswith("http://localhost:3000/bills?payment="))

        st = c.get(f"/api/billing/payments/{pay['payment_id']}/").json()
        self.assertEqual(st["status"], "succeeded")
        self.assertFalse(st["state"]["blocked"])
        inv.refresh_from_db()
        self.assertEqual(inv.status, "paid")

    def test_foreign_return_url_is_replaced(self):
        inv = Invoice.objects.create(user=self.r1, title="X", amount=1, due_date=today())
        c = client_for(self.r1)
        pay = c.post(f"/api/billing/invoices/{inv.pk}/pay/", {"return_url": "https://evil.example/x"}, format="json").json()
        self.assertNotIn("evil", Payment.objects.get(pk=pay["payment_id"]).return_url)

    def test_cannot_pay_someone_elses_invoice(self):
        inv = Invoice.objects.create(user=self.r2, title="X", amount=1, due_date=today())
        self.assertEqual(client_for(self.r1).post(f"/api/billing/invoices/{inv.pk}/pay/").status_code, 404)

    def test_manual_mark_paid_and_cancel(self):
        a = Invoice.objects.create(user=self.r1, title="A", amount=10, due_date=today() - timedelta(days=3), block_on_overdue=True)
        b = Invoice.objects.create(user=self.r1, title="B", amount=10, due_date=today() - timedelta(days=3), block_on_overdue=True)
        self.assertEqual(self.adm.post(f"/api/admin/invoices/{a.pk}/mark-paid/", {"method": "cash"}, format="json").status_code, 200)
        self.assertTrue(self.login(self.r1)["billing"]["blocked"])  # B ещё блокирует
        self.assertEqual(self.adm.post(f"/api/admin/invoices/{b.pk}/cancel/").status_code, 200)
        self.assertFalse(self.login(self.r1)["billing"]["blocked"])
        self.assertEqual(self.adm.post(f"/api/admin/invoices/{b.pk}/cancel/").status_code, 409)

    def test_extending_due_date_unblocks(self):
        inv = Invoice.objects.create(user=self.r1, title="A", amount=10, due_date=today() - timedelta(days=3), block_on_overdue=True)
        self.adm.patch(f"/api/admin/invoices/{inv.pk}/", {"due_date": (today() + timedelta(days=5)).isoformat()}, format="json")
        self.assertFalse(self.login(self.r1)["billing"]["blocked"])

    @override_settings(BILLING_PROVIDER="")
    def test_pay_without_provider(self):
        inv = Invoice.objects.create(user=self.r1, title="X", amount=1, due_date=today())
        self.assertEqual(client_for(self.r1).post(f"/api/billing/invoices/{inv.pk}/pay/").status_code, 400)


@override_settings(BILLING_PROVIDER="demo")
class RealDataEdgeCases(TestCase):
    """Крайние случаи, найденные на реальной базе."""

    def setUp(self):
        self.admin = make_user("admin", role="admin")
        self.adm = client_for(self.admin)
        # как в проде: имени нет, логин «квартира-подъезд»
        self.a2 = make_user("2-1", apartment_no="2", entrance_no=1)
        self.a10 = make_user("10-1", apartment_no="10", entrance_no=1)
        self.truck = make_user("musorovoz", apartment_no="10000", entrance_no=1)
        self.off = make_user("5-1", apartment_no="5")
        self.off.is_active = False
        self.off.save()

    def body(self, **kw):
        b = {"recipients": "parking", "title": "Паркинг", "period": "Декабрь 2026", "amount": "1500",
             "due_date": (today() + timedelta(days=5)).isoformat(), "block_on_overdue": True}
        b.update(kw)
        return b

    def test_bulk_skips_service_and_inactive(self):
        res = self.adm.post("/api/admin/invoices/", self.body(), format="json").json()
        self.assertEqual(res["created"], 2)
        self.assertFalse(Invoice.objects.filter(user__in=[self.truck, self.off]).exists())
        ov = self.adm.get("/api/admin/overview/").json()
        self.assertEqual(ov["parking_total"], 2)

    def test_service_can_be_billed_explicitly(self):
        res = self.adm.post("/api/admin/invoices/", self.body(recipients="users", user_ids=[self.truck.pk]), format="json").json()
        self.assertEqual(res["created"], 1)

    def test_residents_sorted_by_apartment_number(self):
        rows = self.adm.get("/api/admin/residents/").json()["results"]
        self.assertEqual([r["apartment_no"] for r in rows], ["2", "5", "10", "10000"])
        self.assertTrue(rows[-1]["is_service"])

    def test_double_click_reuses_pending_payment(self):
        inv = Invoice.objects.create(user=self.a2, title="X", amount=1, due_date=today())
        c = client_for(self.a2)
        p1 = c.post(f"/api/billing/invoices/{inv.pk}/pay/").json()
        p2 = c.post(f"/api/billing/invoices/{inv.pk}/pay/").json()
        self.assertEqual(p1["payment_id"], p2["payment_id"])
        self.assertEqual(Payment.objects.count(), 1)

    def test_second_payment_flagged_for_refund(self):
        inv = Invoice.objects.create(user=self.a2, title="X", amount=1, due_date=today())
        pay = client_for(self.a2).post(f"/api/billing/invoices/{inv.pk}/pay/").json()
        self.adm.post(f"/api/admin/invoices/{inv.pk}/mark-paid/", {"method": "cash"}, format="json")
        self.client.post(f"/api/billing/demo/{sign_payment(pay['payment_id'])}/", {"action": "pay"})
        self.assertIn("возврат", Payment.objects.get(pk=pay["payment_id"]).note)

    def test_stale_pending_expires(self):
        inv = Invoice.objects.create(user=self.a2, title="X", amount=1, due_date=today())
        p = Payment.objects.create(invoice=inv, amount=1, provider="demo")
        Payment.objects.filter(pk=p.pk).update(created_at=p.created_at - timedelta(days=2))
        self.adm.get("/api/admin/payments/?status=pending")
        p.refresh_from_db()
        self.assertEqual(p.status, "failed")

    def test_due_today_does_not_block_yet(self):
        Invoice.objects.create(user=self.a2, title="X", amount=1, due_date=today(), block_on_overdue=True)
        data = APIClient().post("/api/auth/login/", {"login": "2-1", "password": "pw"}, format="json").json()
        self.assertFalse(data["billing"]["blocked"])


@override_settings(BILLING_PROVIDER="demo")
class BatchTests(TestCase):
    def setUp(self):
        self.adm = client_for(make_user("admin", role="admin"))
        self.users = [make_user(f"{i}-1", apartment_no=str(i)) for i in range(1, 5)]

    def issue(self, **kw):
        b = {"recipients": "parking", "title": "Паркинг", "period": "Декабрь 2026", "amount": "1500",
             "due_date": (today() + timedelta(days=5)).isoformat(), "block_on_overdue": True}
        b.update(kw)
        return self.adm.post("/api/admin/invoices/", b, format="json").json()

    def test_batches_list_with_totals(self):
        res = self.issue()
        self.issue(recipients="users", user_ids=[self.users[0].pk], title="Ремонт", period="")
        inv = Invoice.objects.filter(batch=res["batch"]).first()
        self.adm.post(f"/api/admin/invoices/{inv.pk}/mark-paid/", {"method": "cash"}, format="json")
        rows = self.adm.get("/api/admin/batches/").json()["results"]
        self.assertEqual(len(rows), 2)  # одиночный счёт тоже своё выставление
        b = next(r for r in rows if r["batch"] == res["batch"])
        self.assertEqual((b["total"], b["paid"], b["open"]), (4, 1, 3))
        self.assertEqual((Decimal(b["sum_total"]), Decimal(b["sum_paid"])), (Decimal("6000"), Decimal("1500")))
        listed = self.adm.get(f"/api/admin/invoices/?batch={res['batch']}").json()
        self.assertEqual(listed["count"], 4)

    def test_extend_and_cancel_batch(self):
        res = self.issue()
        new_due = (today() + timedelta(days=20)).isoformat()
        b = self.adm.patch(f"/api/admin/batches/{res['batch']}/", {"due_date": new_due}, format="json").json()
        self.assertEqual(b["due_date"], new_due)
        inv = Invoice.objects.filter(batch=res["batch"]).first()
        inv.mark_paid()
        b = self.adm.post(f"/api/admin/batches/{res['batch']}/cancel/").json()
        self.assertEqual((b["cancelled_now"], b["paid"], b["cancelled"]), (3, 1, 3))


@override_settings(BILLING_PROVIDER="demo")
class DeleteTests(TestCase):
    def setUp(self):
        self.adm = client_for(make_user("admin", role="admin"))
        self.r = [make_user(f"{i}-1", apartment_no=str(i)) for i in range(1, 5)]
        res = self.adm.post("/api/admin/invoices/", {
            "recipients": "parking", "title": "Паркинг", "period": "Декабрь 2026", "amount": "1500",
            "due_date": today().isoformat(), "block_on_overdue": True}, format="json").json()
        self.batch = res["batch"]
        self.inv = list(Invoice.objects.filter(batch=self.batch).order_by("pk"))

    def test_delete_single_unblocks(self):
        Invoice.objects.filter(pk=self.inv[0].pk).update(due_date=today() - timedelta(days=2))
        login = lambda: APIClient().post("/api/auth/login/", {"login": self.inv[0].user.login, "password": "pw"}, format="json").json()
        self.assertTrue(login()["billing"]["blocked"])
        self.assertEqual(self.adm.delete(f"/api/admin/invoices/{self.inv[0].pk}/").status_code, 204)
        self.assertFalse(login()["billing"]["blocked"])

    def test_paid_invoice_cannot_be_deleted(self):
        self.adm.post(f"/api/admin/invoices/{self.inv[0].pk}/mark-paid/", {"method": "cash"}, format="json")
        self.assertEqual(self.adm.delete(f"/api/admin/invoices/{self.inv[0].pk}/").status_code, 409)

    def test_invoice_being_paid_cannot_be_deleted(self):
        client_for(self.inv[0].user).post(f"/api/billing/invoices/{self.inv[0].pk}/pay/")
        self.assertEqual(self.adm.delete(f"/api/admin/invoices/{self.inv[0].pk}/").status_code, 409)

    def test_delete_batch_keeps_paid_and_paying(self):
        self.adm.post(f"/api/admin/invoices/{self.inv[0].pk}/mark-paid/", {"method": "cash"}, format="json")
        client_for(self.inv[1].user).post(f"/api/billing/invoices/{self.inv[1].pk}/pay/")
        self.adm.post(f"/api/admin/invoices/{self.inv[2].pk}/cancel/")
        res = self.adm.delete(f"/api/admin/batches/{self.batch}/").json()
        self.assertEqual((res["deleted"], res["kept_paid"], res["kept_paying"], res["remaining"]), (2, 1, 1, 2))

    def test_delete_whole_batch(self):
        res = self.adm.delete(f"/api/admin/batches/{self.batch}/").json()
        self.assertEqual((res["deleted"], res["remaining"]), (4, 0))
        self.assertEqual(self.adm.get(f"/api/admin/batches/{self.batch}/").status_code, 404)


@override_settings(BILLING_PROVIDER="demo")
class TestPaymentsCleanup(TestCase):
    def test_removes_demo_payments_and_reopens_invoices(self):
        adm = client_for(make_user("admin", role="admin"))
        u = make_user("1-1", apartment_no="1")
        demo_paid = Invoice.objects.create(user=u, title="A", amount=10, due_date=today() - timedelta(days=1), block_on_overdue=True)
        cash_paid = Invoice.objects.create(user=u, title="B", amount=10, due_date=today())
        for inv in (demo_paid,):
            pay = client_for(u).post(f"/api/billing/invoices/{inv.pk}/pay/").json()
            self.client.post(f"/api/billing/demo/{sign_payment(pay['payment_id'])}/", {"action": "pay"})
        adm.post(f"/api/admin/invoices/{cash_paid.pk}/mark-paid/", {"method": "cash"}, format="json")
        self.assertEqual(adm.get("/api/admin/test-payments/").json()["payments"], 1)

        res = adm.delete("/api/admin/test-payments/").json()
        self.assertEqual((res["deleted"], res["reopened"], res["payments"]), (1, 1, 0))
        demo_paid.refresh_from_db(); cash_paid.refresh_from_db()
        self.assertEqual((demo_paid.status, cash_paid.status), ("issued", "paid"))
        # тестовая оплата больше не «снимает» блокировку
        data = APIClient().post("/api/auth/login/", {"login": "1-1", "password": "pw"}, format="json").json()
        self.assertTrue(data["billing"]["blocked"])

    def test_requires_admin(self):
        u = make_user("1-1")
        self.assertEqual(client_for(u).delete("/api/admin/test-payments/").status_code, 403)
