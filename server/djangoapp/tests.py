"""
RBAC integration test matrix.

Covers every role × every protected endpoint:
  - ANONYMOUS  (no token)
  - CUSTOMER   (valid token, role=CUSTOMER)
  - DEALER_ADMIN (valid token, role=DEALER_ADMIN, assigned_dealer_id=1)
  - ADMIN      (valid token, role=ADMIN)

All upstream service calls (get_request, post_review, put_request,
delete_request) are mocked so the Node.js database API is not required.

Run with:
    python manage.py test djangoapp.tests
"""

import json
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from .views import issue_tokens

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEALER_STUB = {"id": 1, "full_name": "Test Dealer", "city": "Testville", "state": "TX"}
REVIEW_STUB = {"id": 1, "dealership": 1, "review": "Great!", "author_id": None, "author_username": None}
UPDATE_OK = {"id": 1, "full_name": "Updated"}


def auth_header(user):
    tokens = issue_tokens(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {tokens['access']}"}


def json_body(data):
    return json.dumps(data)


def make_review_stub(author_id, author_username="testuser"):
    return {**REVIEW_STUB, "author_id": author_id, "author_username": author_username}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class RbacTestBase(TestCase):
    def setUp(self):
        self.client = Client()

        self.admin = User.objects.create_user(
            username="admin_user",
            password="AdminPass1!",
            email="admin@test.com",
            role=User.Roles.ADMIN,
        )
        # Superuser also gets ADMIN via UserManager
        self.superuser = User.objects.create_superuser(
            username="super_user",
            password="SuperPass1!",
            email="super@test.com",
        )
        self.customer = User.objects.create_user(
            username="customer_user",
            password="CustPass1!",
            email="cust@test.com",
            role=User.Roles.CUSTOMER,
        )
        self.dealer_admin = User.objects.create_user(
            username="dealer_admin_user",
            password="DealerPass1!",
            email="dealer@test.com",
            role=User.Roles.DEALER_ADMIN,
            assigned_dealer_id=1,
        )
        self.dealer_admin_2 = User.objects.create_user(
            username="dealer_admin_2",
            password="DealerPass2!",
            email="dealer2@test.com",
            role=User.Roles.DEALER_ADMIN,
            assigned_dealer_id=2,
        )


# ---------------------------------------------------------------------------
# 1.  Auth endpoints
# ---------------------------------------------------------------------------

class AuthTests(RbacTestBase):

    def test_login_success_returns_tokens_and_profile(self):
        resp = self.client.post(
            "/djangoapp/login/",
            json_body({"userName": "customer_user", "password": "CustPass1!"}),
            content_type="application/json",
        )
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("tokens", data)
        self.assertIn("access", data["tokens"])
        self.assertEqual(data["user"]["role"], User.Roles.CUSTOMER)

    def test_login_wrong_password_returns_401(self):
        resp = self.client.post(
            "/djangoapp/login/",
            json_body({"userName": "customer_user", "password": "wrong"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "INVALID_CREDENTIALS")

    def test_login_missing_fields_returns_400(self):
        resp = self.client.post(
            "/djangoapp/login/",
            json_body({"userName": "customer_user"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "MISSING_FIELDS")

    def test_login_rejects_get(self):
        resp = self.client.get("/djangoapp/login/")
        self.assertEqual(resp.status_code, 405)

    def test_registration_creates_customer_and_returns_201(self):
        resp = self.client.post(
            "/djangoapp/register/",
            json_body({"userName": "new_user", "password": "NewPass1!"}),
            content_type="application/json",
        )
        data = resp.json()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(data["user"]["role"], User.Roles.CUSTOMER)
        self.assertIsNone(data["user"]["assignedDealerId"])

    def test_registration_ignores_client_supplied_role(self):
        resp = self.client.post(
            "/djangoapp/register/",
            json_body({"userName": "hacker", "password": "Pass1!", "role": "ADMIN"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["user"]["role"], User.Roles.CUSTOMER)

    def test_registration_duplicate_username_returns_409(self):
        resp = self.client.post(
            "/djangoapp/register/",
            json_body({"userName": "customer_user", "password": "AnyPass1!"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"]["code"], "USERNAME_TAKEN")

    def test_registration_missing_fields_returns_400(self):
        resp = self.client.post(
            "/djangoapp/register/",
            json_body({"userName": "only_name"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# 2.  Admin — create dealer admin
# ---------------------------------------------------------------------------

class CreateDealerAdminTests(RbacTestBase):

    def _post(self, user, payload):
        headers = auth_header(user) if user else {}
        return self.client.post(
            "/djangoapp/admin/create_dealer_admin",
            json_body(payload),
            content_type="application/json",
            **headers,
        )

    def test_admin_can_create_dealer_admin(self):
        resp = self._post(self.admin, {
            "userName": "new_dealer_admin",
            "password": "Pass1!",
            "assignedDealerId": 5,
        })
        data = resp.json()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(data["user"]["role"], User.Roles.DEALER_ADMIN)
        self.assertEqual(data["user"]["assignedDealerId"], 5)

    def test_superuser_can_create_dealer_admin(self):
        resp = self._post(self.superuser, {
            "userName": "another_dealer_admin",
            "password": "Pass1!",
            "assignedDealerId": 6,
        })
        self.assertEqual(resp.status_code, 201)

    def test_customer_cannot_create_dealer_admin(self):
        resp = self._post(self.customer, {
            "userName": "bad_actor",
            "password": "Pass1!",
            "assignedDealerId": 5,
        })
        self.assertEqual(resp.status_code, 403)

    def test_dealer_admin_cannot_create_dealer_admin(self):
        resp = self._post(self.dealer_admin, {
            "userName": "bad_actor_2",
            "password": "Pass1!",
            "assignedDealerId": 5,
        })
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_cannot_create_dealer_admin(self):
        resp = self._post(None, {
            "userName": "anon_attempt",
            "password": "Pass1!",
            "assignedDealerId": 5,
        })
        self.assertEqual(resp.status_code, 401)

    def test_missing_dealer_id_returns_400(self):
        resp = self._post(self.admin, {"userName": "da", "password": "Pass1!"})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_dealer_id_returns_400(self):
        resp = self._post(self.admin, {
            "userName": "da",
            "password": "Pass1!",
            "assignedDealerId": -1,
        })
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_username_returns_409(self):
        resp = self._post(self.admin, {
            "userName": "customer_user",
            "password": "Pass1!",
            "assignedDealerId": 3,
        })
        self.assertEqual(resp.status_code, 409)


# ---------------------------------------------------------------------------
# 3.  Dealership read (anonymous allowed)
# ---------------------------------------------------------------------------

MOCK_DEALERS = [DEALER_STUB]
MOCK_DEALER = [DEALER_STUB]


class DealershipReadTests(RbacTestBase):

    @patch("djangoapp.views.get_request", return_value=MOCK_DEALERS)
    def test_anonymous_can_list_dealers(self, _mock):
        resp = self.client.get("/djangoapp/get_dealers")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("dealers", resp.json())

    @patch("djangoapp.views.get_request", return_value=MOCK_DEALERS)
    def test_customer_can_list_dealers(self, _mock):
        resp = self.client.get("/djangoapp/get_dealers", **auth_header(self.customer))
        self.assertEqual(resp.status_code, 200)

    @patch("djangoapp.views.get_request", return_value=MOCK_DEALER)
    def test_anonymous_can_get_dealer_details(self, _mock):
        resp = self.client.get("/djangoapp/dealer/1")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("dealer", resp.json())

    @patch("djangoapp.views.get_request", return_value=MOCK_DEALER)
    def test_dealer_admin_can_get_dealer_details(self, _mock):
        resp = self.client.get("/djangoapp/dealer/1", **auth_header(self.dealer_admin))
        self.assertEqual(resp.status_code, 200)

    @patch("djangoapp.views.get_request", return_value=MOCK_DEALERS)
    def test_anonymous_can_list_dealers_by_state(self, _mock):
        resp = self.client.get("/djangoapp/get_dealers/TX")
        self.assertEqual(resp.status_code, 200)

    def test_bad_token_on_read_endpoint_returns_401(self):
        resp = self.client.get(
            "/djangoapp/get_dealers",
            HTTP_AUTHORIZATION="Bearer not-a-real-token",
        )
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# 4.  Review read (anonymous allowed)
# ---------------------------------------------------------------------------

MOCK_REVIEWS = [make_review_stub(author_id=1)]


class ReviewReadTests(RbacTestBase):

    @patch("djangoapp.views.get_request", return_value=MOCK_REVIEWS)
    @patch("djangoapp.views.analyze_review_sentiments", return_value={"sentiment": "positive"})
    def test_anonymous_can_read_reviews(self, _sent, _get):
        resp = self.client.get("/djangoapp/reviews/dealer/1")
        self.assertEqual(resp.status_code, 200)
        reviews = resp.json()["reviews"]
        self.assertEqual(reviews[0]["sentiment"], "positive")

    @patch("djangoapp.views.get_request", return_value=MOCK_REVIEWS)
    @patch("djangoapp.views.analyze_review_sentiments", return_value={"sentiment": "neutral"})
    def test_customer_can_read_reviews(self, _sent, _get):
        resp = self.client.get(
            "/djangoapp/reviews/dealer/1",
            **auth_header(self.customer),
        )
        self.assertEqual(resp.status_code, 200)

    @patch("djangoapp.views.get_request", return_value=MOCK_REVIEWS)
    @patch("djangoapp.views.analyze_review_sentiments",
           return_value={"ok": False, "error": {"service": "sentiment-analyzer", "message": "down"}})
    def test_sentiment_failure_falls_back_to_neutral(self, _sent, _get):
        resp = self.client.get("/djangoapp/reviews/dealer/1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reviews"][0]["sentiment"], "neutral")
        self.assertTrue(resp.json()["reviews"][0].get("sentiment_error"))


# ---------------------------------------------------------------------------
# 5.  Review create
# ---------------------------------------------------------------------------

REVIEW_PAYLOAD = {
    "dealership": 1,
    "review": "Loved it",
    "purchase": True,
    "purchase_date": "2024-01-01",
    "car_make": "Toyota",
    "car_model": "Camry",
    "car_year": 2022,
    "name": "Test User",
}


class ReviewCreateTests(RbacTestBase):

    def _post(self, user, payload=None):
        headers = auth_header(user) if user else {}
        return self.client.post(
            "/djangoapp/add_review",
            json_body(payload or REVIEW_PAYLOAD),
            content_type="application/json",
            **headers,
        )

    @patch("djangoapp.views.post_review", return_value={"id": 99})
    def test_customer_can_create_review(self, mock_post):
        resp = self._post(self.customer)
        self.assertEqual(resp.status_code, 200)
        # Authorship is stamped onto the forwarded payload
        call_data = mock_post.call_args[0][0]
        self.assertEqual(call_data["author_id"], self.customer.id)
        self.assertEqual(call_data["author_username"], self.customer.username)

    @patch("djangoapp.views.post_review", return_value={"id": 99})
    def test_admin_can_create_review(self, _mock):
        resp = self._post(self.admin)
        self.assertEqual(resp.status_code, 200)

    def test_dealer_admin_cannot_create_review(self):
        resp = self._post(self.dealer_admin)
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_cannot_create_review(self):
        resp = self._post(None)
        self.assertEqual(resp.status_code, 401)

    def test_invalid_json_returns_400(self):
        resp = self.client.post(
            "/djangoapp/add_review",
            "not-json",
            content_type="application/json",
            **auth_header(self.customer),
        )
        self.assertEqual(resp.status_code, 400)

    def test_get_method_returns_405(self):
        resp = self.client.get("/djangoapp/add_review", **auth_header(self.customer))
        self.assertEqual(resp.status_code, 405)


# ---------------------------------------------------------------------------
# 6.  Review update
# ---------------------------------------------------------------------------

UPDATE_REVIEW_PAYLOAD = {"review": "Updated text"}


class ReviewUpdateTests(RbacTestBase):

    def _put(self, user, review_id, payload=None):
        headers = auth_header(user) if user else {}
        return self.client.put(
            f"/djangoapp/reviews/{review_id}/update",
            json_body(payload or UPDATE_REVIEW_PAYLOAD),
            content_type="application/json",
            **headers,
        )

    @patch("djangoapp.views.put_request", return_value=UPDATE_OK)
    @patch("djangoapp.views.get_request", return_value=make_review_stub(author_id=None))
    def test_admin_can_update_any_review(self, _get, _put):
        # get_request stub is not called for admin (update.any bypasses ownership check)
        resp = self._put(self.admin, review_id=1)
        self.assertEqual(resp.status_code, 200)
        _get.assert_not_called()

    @patch("djangoapp.views.put_request", return_value=UPDATE_OK)
    def test_customer_can_update_own_review(self, _put):
        own_stub = make_review_stub(author_id=self.customer.id)
        with patch("djangoapp.views.get_request", return_value=own_stub):
            resp = self._put(self.customer, review_id=1)
        self.assertEqual(resp.status_code, 200)

    def test_customer_cannot_update_others_review(self):
        other_stub = make_review_stub(author_id=self.admin.id)
        with patch("djangoapp.views.get_request", return_value=other_stub):
            resp = self._put(self.customer, review_id=1)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "FORBIDDEN")

    def test_dealer_admin_cannot_update_any_review(self):
        resp = self._put(self.dealer_admin, review_id=1)
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_cannot_update_review(self):
        resp = self._put(None, review_id=1)
        self.assertEqual(resp.status_code, 401)

    def test_no_update_fields_returns_400(self):
        own_stub = make_review_stub(author_id=self.customer.id)
        with patch("djangoapp.views.get_request", return_value=own_stub):
            resp = self._put(self.customer, review_id=1, payload={"unknown_field": "x"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "NO_UPDATE_FIELDS")

    def test_review_not_found_returns_404(self):
        with patch("djangoapp.views.get_request", return_value=None):
            resp = self._put(self.customer, review_id=999)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"]["code"], "REVIEW_NOT_FOUND")


# ---------------------------------------------------------------------------
# 7.  Review delete
# ---------------------------------------------------------------------------

class ReviewDeleteTests(RbacTestBase):

    def _delete(self, user, review_id):
        headers = auth_header(user) if user else {}
        return self.client.delete(
            f"/djangoapp/reviews/{review_id}/delete",
            **headers,
        )

    @patch("djangoapp.views.delete_request", return_value={"message": "Review deleted."})
    def test_admin_can_delete_any_review(self, _del):
        resp = self._delete(self.admin, review_id=1)
        self.assertEqual(resp.status_code, 200)

    @patch("djangoapp.views.delete_request", return_value={"message": "Review deleted."})
    def test_customer_can_delete_own_review(self, _del):
        own_stub = make_review_stub(author_id=self.customer.id)
        with patch("djangoapp.views.get_request", return_value=own_stub):
            resp = self._delete(self.customer, review_id=1)
        self.assertEqual(resp.status_code, 200)

    def test_customer_cannot_delete_others_review(self):
        other_stub = make_review_stub(author_id=self.admin.id)
        with patch("djangoapp.views.get_request", return_value=other_stub):
            resp = self._delete(self.customer, review_id=1)
        self.assertEqual(resp.status_code, 403)

    def test_dealer_admin_cannot_delete_review(self):
        resp = self._delete(self.dealer_admin, review_id=1)
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_cannot_delete_review(self):
        resp = self._delete(None, review_id=1)
        self.assertEqual(resp.status_code, 401)

    def test_wrong_method_returns_405(self):
        resp = self.client.post(
            "/djangoapp/reviews/1/delete",
            **auth_header(self.admin),
        )
        self.assertEqual(resp.status_code, 405)


# ---------------------------------------------------------------------------
# 8.  Dealership update
# ---------------------------------------------------------------------------

UPDATE_DEALER_PAYLOAD = {"city": "New City"}


class DealershipUpdateTests(RbacTestBase):

    def _put(self, user, dealer_id, payload=None):
        headers = auth_header(user) if user else {}
        return self.client.put(
            f"/djangoapp/dealer/{dealer_id}/update",
            json_body(payload or UPDATE_DEALER_PAYLOAD),
            content_type="application/json",
            **headers,
        )

    @patch("djangoapp.views.put_request", return_value=UPDATE_OK)
    def test_admin_can_update_any_dealer(self, _put):
        resp = self._put(self.admin, dealer_id=99)
        self.assertEqual(resp.status_code, 200)

    @patch("djangoapp.views.put_request", return_value=UPDATE_OK)
    def test_dealer_admin_can_update_own_dealer(self, _put):
        # dealer_admin has assigned_dealer_id=1
        resp = self._put(self.dealer_admin, dealer_id=1)
        self.assertEqual(resp.status_code, 200)

    def test_dealer_admin_cannot_update_other_dealer(self):
        # dealer_admin_2 has assigned_dealer_id=2, trying to update dealer 1
        resp = self._put(self.dealer_admin_2, dealer_id=1)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "FORBIDDEN")

    def test_customer_cannot_update_dealer(self):
        resp = self._put(self.customer, dealer_id=1)
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_cannot_update_dealer(self):
        resp = self._put(None, dealer_id=1)
        self.assertEqual(resp.status_code, 401)

    def test_no_update_fields_returns_400(self):
        resp = self._put(self.admin, dealer_id=1, payload={"id": 999})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "NO_UPDATE_FIELDS")

    def test_invalid_json_returns_400(self):
        resp = self.client.put(
            "/djangoapp/dealer/1/update",
            "not-json",
            content_type="application/json",
            **auth_header(self.admin),
        )
        self.assertEqual(resp.status_code, 400)

    def test_wrong_method_returns_405(self):
        resp = self.client.post(
            "/djangoapp/dealer/1/update",
            **auth_header(self.admin),
        )
        self.assertEqual(resp.status_code, 405)


# ---------------------------------------------------------------------------
# 9.  Upstream service error propagation
# ---------------------------------------------------------------------------

UPSTREAM_ERROR = {
    "ok": False,
    "status": 503,
    "error": {
        "service": "database-api",
        "message": "Database unavailable.",
    },
}


class UpstreamErrorTests(RbacTestBase):

    @patch("djangoapp.views.get_request", return_value=UPSTREAM_ERROR)
    def test_upstream_error_on_dealers_list_is_surfaced(self, _mock):
        resp = self.client.get("/djangoapp/get_dealers")
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertIn("error", body)
        self.assertEqual(body["error"]["code"], "DATABASE_API_ERROR")
        # Internal service details must not leak raw "ok: false" envelope
        self.assertNotIn("ok", body)

    @patch("djangoapp.views.get_request", return_value=UPSTREAM_ERROR)
    def test_upstream_error_on_dealer_details_is_surfaced(self, _mock):
        resp = self.client.get("/djangoapp/dealer/1")
        self.assertEqual(resp.status_code, 503)

    @patch("djangoapp.views.get_request", return_value=UPSTREAM_ERROR)
    @patch("djangoapp.views.analyze_review_sentiments", return_value={"sentiment": "neutral"})
    def test_upstream_error_on_reviews_is_surfaced(self, _sent, _get):
        resp = self.client.get("/djangoapp/reviews/dealer/1")
        self.assertEqual(resp.status_code, 503)

    @patch("djangoapp.views.post_review", return_value=UPSTREAM_ERROR)
    def test_upstream_error_on_add_review_is_surfaced(self, _mock):
        resp = self.client.post(
            "/djangoapp/add_review",
            json_body(REVIEW_PAYLOAD),
            content_type="application/json",
            **auth_header(self.customer),
        )
        self.assertEqual(resp.status_code, 503)

    @patch("djangoapp.views.put_request", return_value=UPSTREAM_ERROR)
    def test_upstream_error_on_update_dealer_is_surfaced(self, _mock):
        resp = self.client.put(
            "/djangoapp/dealer/1/update",
            json_body(UPDATE_DEALER_PAYLOAD),
            content_type="application/json",
            **auth_header(self.admin),
        )
        self.assertEqual(resp.status_code, 503)

    @patch("djangoapp.views.put_request", return_value=UPSTREAM_ERROR)
    @patch("djangoapp.views.get_request", return_value=make_review_stub(author_id=None))
    def test_upstream_error_on_update_review_is_surfaced(self, _get, _put):
        resp = self.client.put(
            "/djangoapp/reviews/1/update",
            json_body(UPDATE_REVIEW_PAYLOAD),
            content_type="application/json",
            **auth_header(self.admin),
        )
        self.assertEqual(resp.status_code, 503)

    @patch("djangoapp.views.delete_request", return_value=UPSTREAM_ERROR)
    def test_upstream_error_on_delete_review_is_surfaced(self, _mock):
        resp = self.client.delete(
            "/djangoapp/reviews/1/delete",
            **auth_header(self.admin),
        )
        self.assertEqual(resp.status_code, 503)


# ---------------------------------------------------------------------------
# 10.  Token edge cases
# ---------------------------------------------------------------------------

class TokenEdgeCaseTests(RbacTestBase):

    def test_expired_token_returns_401(self):
        import jwt as pyjwt
        from django.conf import settings
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        payload = {
            "sub": str(self.customer.id),
            "username": self.customer.username,
            "role": self.customer.role,
            "assigned_dealer_id": None,
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "type": "access",
            "exp": int((now - timedelta(hours=1)).timestamp()),  # already expired
        }
        expired_token = pyjwt.encode(payload, settings.JWT_SIGNING_KEY, algorithm=settings.JWT_ALGORITHM)
        resp = self.client.get(
            "/djangoapp/get_dealers",
            HTTP_AUTHORIZATION=f"Bearer {expired_token}",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "TOKEN_EXPIRED")

    def test_refresh_token_rejected_on_protected_endpoint(self):
        tokens = issue_tokens(self.customer)
        resp = self.client.post(
            "/djangoapp/add_review",
            json_body(REVIEW_PAYLOAD),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['refresh']}",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "WRONG_TOKEN_TYPE")

    def test_malformed_token_returns_401(self):
        resp = self.client.get(
            "/djangoapp/get_dealers",
            HTTP_AUTHORIZATION="Bearer this.is.garbage",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "INVALID_TOKEN")

    def test_missing_bearer_prefix_returns_401(self):
        tokens = issue_tokens(self.customer)
        resp = self.client.post(
            "/djangoapp/add_review",
            json_body(REVIEW_PAYLOAD),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tokens['access']}",  # wrong scheme
        )
        self.assertEqual(resp.status_code, 401)
