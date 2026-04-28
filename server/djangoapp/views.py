from django.contrib.auth import logout
from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth import login, authenticate, get_user_model
from django.utils import timezone
import logging
import json
import jwt
from django.views.decorators.csrf import csrf_exempt
from .models import CarMake, CarModel
from .restapis import get_request, analyze_review_sentiments, post_review, put_request, delete_request
from .populate import initiate

User = get_user_model()


def build_user_profile(user):
    return {
        "id": user.id,
        "userName": user.username,
        "email": user.email,
        "role": user.role,
        "assignedDealerId": user.assigned_dealer_id,
    }


def issue_tokens(user):
    now = timezone.now()
    access_exp = now + settings.JWT_ACCESS_TTL
    refresh_exp = now + settings.JWT_REFRESH_TTL

    base_claims = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "assigned_dealer_id": user.assigned_dealer_id,
        "iat": int(now.timestamp()),
    }

    access_payload = {
        **base_claims,
        "type": "access",
        "exp": int(access_exp.timestamp()),
    }
    refresh_payload = {
        **base_claims,
        "type": "refresh",
        "exp": int(refresh_exp.timestamp()),
    }

    access_token = jwt.encode(
        access_payload,
        settings.JWT_SIGNING_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    refresh_token = jwt.encode(
        refresh_payload,
        settings.JWT_SIGNING_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return {
        "access": access_token,
        "refresh": refresh_token,
        "accessExpiresAt": access_exp.isoformat(),
        "refreshExpiresAt": refresh_exp.isoformat(),
    }


def get_bearer_token(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    return token or None


def get_authenticated_user_from_token(request):
    token = get_bearer_token(request)
    if not token:
        return None, api_error(401, "MISSING_TOKEN", "Missing Bearer token")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SIGNING_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        return None, api_error(401, "TOKEN_EXPIRED", "Token expired")
    except jwt.InvalidTokenError:
        return None, api_error(401, "INVALID_TOKEN", "Invalid token")

    if payload.get("type") != "access":
        return None, api_error(401, "WRONG_TOKEN_TYPE", "Access token required")

    user_id = payload.get("sub")
    if not user_id:
        return None, api_error(401, "INVALID_TOKEN_SUBJECT", "Invalid token subject")

    try:
        user = User.objects.get(id=user_id)
        return user, None
    except User.DoesNotExist:
        return None, api_error(401, "USER_NOT_FOUND", "User not found")


def require_admin_user(request):
    user, error_response = get_authenticated_user_from_token(request)
    if error_response is not None:
        return None, error_response

    if user.role != User.Roles.ADMIN and not user.is_superuser:
        return None, api_error(403, "FORBIDDEN", "Admin role required")

    return user, None


# Central RBAC capability map.
# Later parts will wire these capabilities into protected endpoints.
ROLE_CAPABILITIES = {
    "ADMIN": {
        "dealership.read",
        "dealership.create",
        "dealership.update.any",
        "dealership.delete",
        "review.read",
        "review.create",
        "review.update.any",
        "review.delete.any",
    },
    "DEALER_ADMIN": {
        "dealership.read",
        "dealership.update.own",
        "review.read",
    },
    "CUSTOMER": {
        "dealership.read",
        "review.read",
        "review.create",
        "review.update.own",
        "review.delete.own",
    },
    "ANONYMOUS": {
        "dealership.read",
        "review.read",
    },
}


def resolve_role(user):
    if user is None or getattr(user, "is_anonymous", True):
        return "ANONYMOUS"
    if getattr(user, "is_superuser", False):
        return "ADMIN"
    return getattr(user, "role", "CUSTOMER")


def has_capability(user, capability):
    role = resolve_role(user)
    return capability in ROLE_CAPABILITIES.get(role, set())


def get_optional_authenticated_user(request):
    """Return authenticated user if bearer token exists, otherwise anonymous context."""
    token = get_bearer_token(request)
    if not token:
        return None, None

    user, error_response = get_authenticated_user_from_token(request)
    if error_response is not None:
        return None, error_response

    return user, None


def require_capability(request, capability):
    """Strict guard for authenticated actions that require a specific capability."""
    user, error_response = get_authenticated_user_from_token(request)
    if error_response is not None:
        return None, error_response

    if not has_capability(user, capability):
        return None, api_error(403, "FORBIDDEN", f"Forbidden: missing capability '{capability}'")

    return user, None


def allow_read_capability(request, capability):
    """Guard for read endpoints where anonymous access is allowed."""
    user, error_response = get_optional_authenticated_user(request)
    if error_response is not None:
        return None, error_response

    if not has_capability(user, capability):
        return None, api_error(403, "FORBIDDEN", f"Forbidden: missing capability '{capability}'")

    return user, None


def is_upstream_error(payload):
    return (
        isinstance(payload, dict)
        and payload.get("ok") is False
        and "error" in payload
    )


def api_error(status, code, message):
    """Return a standardised JSON error envelope."""
    return JsonResponse(
        {"status": status, "error": {"code": code, "message": message}},
        status=status,
    )


def upstream_error_response(payload):
    """Translate a restapis service_error into a clean client-facing error."""
    http_status = payload.get("status", 502)
    inner = payload.get("error", {})
    message = inner.get("message", "An upstream service error occurred.")
    service = inner.get("service", "upstream")
    code = service.upper().replace("-", "_") + "_ERROR"
    return api_error(http_status, code, message)


# Get Cars list
def get_cars(request):
    count = CarMake.objects.filter().count()
    print(count)
    if count == 0:
        initiate()
    car_models = CarModel.objects.select_related("car_make")
    cars = []
    for car_model in car_models:
        cars.append({
            "CarModel": car_model.name,
            "CarMake": car_model.car_make.name
        })
    return JsonResponse({"CarModels": cars})


# Get an instance of a logger
logger = logging.getLogger(__name__)


# Create your views here.


# Create a `login_request` view to handle sign in request
@csrf_exempt
def login_user(request):
    if request.method != "POST":
        return api_error(405, "METHOD_NOT_ALLOWED", "Method Not Allowed")

    # Get username and password from request.POST dictionary
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return api_error(400, "INVALID_JSON", "Invalid JSON body")

    username = data.get("userName")
    password = data.get("password")
    if not username or not password:
        return api_error(400, "MISSING_FIELDS", "userName and password are required")

    # Try to check if provide credential can be authenticated
    user = authenticate(username=username, password=password)
    if user is not None:
        # If user is valid, call login method to login current user
        login(request, user)

        tokens = issue_tokens(user)
        return JsonResponse(
            {
                "status": 200,
                "message": "Authenticated",
                "user": build_user_profile(user),
                "tokens": tokens,
            }
        )

    return api_error(401, "INVALID_CREDENTIALS", "Invalid credentials")


# logout_request view
def logout_request(request):
    logout(request)  # Terminate user session
    data = {"userName": ""}  # Return empty username
    return JsonResponse(data)


# registration view to handle sign up request
@csrf_exempt
def registration(request):
    if request.method != "POST":
        return api_error(405, "METHOD_NOT_ALLOWED", "Method Not Allowed")

    # Load JSON data from the request body
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return api_error(400, "INVALID_JSON", "Invalid JSON body")

    username = data.get("userName")
    password = data.get("password")
    first_name = data.get("firstName", "")
    last_name = data.get("lastName", "")
    email = data.get("email", "")

    if not username or not password:
        return api_error(400, "MISSING_FIELDS", "userName and password are required")

    username_exist = False
    try:
        # Check if user already exists
        User.objects.get(username=username)
        username_exist = True
    except User.DoesNotExist:
        # If not, simply log this is a new user
        logger.debug("{} is new user".format(username))

    # If it is a new user
    if not username_exist:
        # Public registration always creates customer accounts and ignores
        # any client-provided role/assigned dealer fields.
        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password,
            email=email,
            role=User.Roles.CUSTOMER,
            assigned_dealer_id=None,
        )
        login(request, user)

        tokens = issue_tokens(user)
        return JsonResponse(
            {
                "status": 201,
                "message": "Registered",
                "user": build_user_profile(user),
                "tokens": tokens,
            },
            status=201,
        )
    else:
        return api_error(409, "USERNAME_TAKEN", f"Username '{username}' is already registered")


@csrf_exempt
def create_dealer_admin(request):
    if request.method != "POST":
        return api_error(405, "METHOD_NOT_ALLOWED", "Method Not Allowed")

    _, error_response = require_admin_user(request)
    if error_response is not None:
        return error_response

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return api_error(400, "INVALID_JSON", "Invalid JSON body")

    username = data.get("userName")
    password = data.get("password")
    first_name = data.get("firstName", "")
    last_name = data.get("lastName", "")
    email = data.get("email", "")
    assigned_dealer_id = data.get("assignedDealerId")

    if not username or not password or not assigned_dealer_id:
        return api_error(400, "MISSING_FIELDS", "userName, password, and assignedDealerId are required")

    try:
        assigned_dealer_id = int(assigned_dealer_id)
        if assigned_dealer_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return api_error(400, "INVALID_DEALER_ID", "assignedDealerId must be a positive integer")

    if User.objects.filter(username=username).exists():
        return api_error(409, "USERNAME_TAKEN", f"Username '{username}' is already registered")

    user = User.objects.create_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
        password=password,
        email=email,
        role=User.Roles.DEALER_ADMIN,
        assigned_dealer_id=assigned_dealer_id,
    )

    return JsonResponse(
        {
            "status": 201,
            "message": "Dealer admin created",
            "user": build_user_profile(user),
        },
        status=201,
    )


# Fetch dealerships from API view
def get_dealerships(request, state="All"):
    _, error_response = allow_read_capability(request, "dealership.read")
    if error_response is not None:
        return error_response

    if state == "All":
        endpoint = "/fetchDealers"
    else:
        endpoint = "/fetchDealers/" + state
    dealerships = get_request(endpoint)
    if is_upstream_error(dealerships):
        return upstream_error_response(dealerships)
    return JsonResponse({"status": 200, "dealers": dealerships})


# Get dealer details view
def get_dealer_details(request, dealer_id):
    _, error_response = allow_read_capability(request, "dealership.read")
    if error_response is not None:
        return error_response

    if dealer_id:
        endpoint = "/fetchDealer/" + str(dealer_id)
        dealership = get_request(endpoint)
        if is_upstream_error(dealership):
            return upstream_error_response(dealership)
        return JsonResponse({"status": 200, "dealer": dealership})
    else:
        return api_error(400, "MISSING_DEALER_ID", "dealer_id is required")


# Get dealer reviews view
def get_dealer_reviews(request, dealer_id):
    _, error_response = allow_read_capability(request, "review.read")
    if error_response is not None:
        return error_response

    # if dealer id has been provided
    if dealer_id:
        endpoint = "/fetchReviews/dealer/" + str(dealer_id)
        reviews = get_request(endpoint)
        if is_upstream_error(reviews):
            return upstream_error_response(reviews)
        for review_detail in reviews:
            response = analyze_review_sentiments(review_detail["review"])
            if is_upstream_error(response):
                review_detail["sentiment"] = "neutral"
                review_detail["sentiment_error"] = True
            else:
                review_detail["sentiment"] = response.get("sentiment", "neutral")
        return JsonResponse({"status": 200, "reviews": reviews})
    else:
        return api_error(400, "MISSING_DEALER_ID", "dealer_id is required")


# Update dealership view
@csrf_exempt
def update_dealership(request, dealer_id):
    if request.method != "PUT":
        return api_error(405, "METHOD_NOT_ALLOWED", "Method Not Allowed")

    # Require the caller to hold at least one of the two update capabilities.
    user, error_response = get_authenticated_user_from_token(request)
    if error_response is not None:
        return error_response

    can_update_any = has_capability(user, "dealership.update.any")
    can_update_own = has_capability(user, "dealership.update.own")

    if not can_update_any and not can_update_own:
        return api_error(403, "FORBIDDEN", "Insufficient role to update dealerships")

    # DEALER_ADMIN can only update their own assigned dealership.
    if can_update_own and not can_update_any:
        if user.assigned_dealer_id != dealer_id:
            return api_error(403, "FORBIDDEN", "You may only update your assigned dealership")

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return api_error(400, "INVALID_JSON", "Invalid JSON body")

    # Strip fields that are not part of the dealership schema to avoid
    # accidental overwrites of id or other non-updatable fields.
    UPDATABLE_FIELDS = {"city", "state", "address", "zip", "lat", "long", "short_name", "full_name"}
    payload = {k: v for k, v in data.items() if k in UPDATABLE_FIELDS}

    if not payload:
        return api_error(400, "NO_UPDATE_FIELDS", "At least one updatable field must be provided")

    response = put_request("/updateDealer/" + str(dealer_id), payload)
    if is_upstream_error(response):
        return upstream_error_response(response)
    return JsonResponse({"status": 200, "dealer": response})


# Add new review view
@csrf_exempt
def add_review(request):
    if request.method != "POST":
        return api_error(405, "METHOD_NOT_ALLOWED", "Method Not Allowed")

    user, error_response = require_capability(request, "review.create")
    if error_response is not None:
        return error_response

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return api_error(400, "INVALID_JSON", "Invalid JSON body")

    # Stamp authorship so ownership checks work on edit/delete
    data["author_id"] = user.id
    data["author_username"] = user.username

    response = post_review(data)
    if is_upstream_error(response):
        return upstream_error_response(response)
    return JsonResponse({"status": 200})


# Update an existing review
@csrf_exempt
def update_review(request, review_id):
    if request.method != "PUT":
        return api_error(405, "METHOD_NOT_ALLOWED", "Method Not Allowed")

    user, error_response = get_authenticated_user_from_token(request)
    if error_response is not None:
        return error_response

    can_update_any = has_capability(user, "review.update.any")
    can_update_own = has_capability(user, "review.update.own")

    if not can_update_any and not can_update_own:
        return api_error(403, "FORBIDDEN", "Insufficient role to update reviews")

    # For own-only roles (CUSTOMER), verify authorship via the stored record.
    if can_update_own and not can_update_any:
        existing = get_request("/fetchReview/" + str(review_id))
        if is_upstream_error(existing):
            return upstream_error_response(existing)
        # existing is expected to be a single document dict or None
        record = existing if isinstance(existing, dict) else (existing[0] if existing else None)
        if not record:
            return api_error(404, "REVIEW_NOT_FOUND", "Review not found")
        if record.get("author_id") != user.id:
            return api_error(403, "FORBIDDEN", "You may only update your own reviews")

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return api_error(400, "INVALID_JSON", "Invalid JSON body")

    UPDATABLE_FIELDS = {"review", "purchase", "purchase_date", "car_make", "car_model", "car_year"}
    payload = {k: v for k, v in data.items() if k in UPDATABLE_FIELDS}

    if not payload:
        return api_error(400, "NO_UPDATE_FIELDS", "At least one updatable field must be provided")

    response = put_request("/updateReview/" + str(review_id), payload)
    if is_upstream_error(response):
        return upstream_error_response(response)
    return JsonResponse({"status": 200, "review": response})


# Delete a review
@csrf_exempt
def delete_review(request, review_id):
    if request.method != "DELETE":
        return api_error(405, "METHOD_NOT_ALLOWED", "Method Not Allowed")

    user, error_response = get_authenticated_user_from_token(request)
    if error_response is not None:
        return error_response

    can_delete_any = has_capability(user, "review.delete.any")
    can_delete_own = has_capability(user, "review.delete.own")

    if not can_delete_any and not can_delete_own:
        return api_error(403, "FORBIDDEN", "Insufficient role to delete reviews")

    # For own-only roles (CUSTOMER), verify authorship via the stored record.
    if can_delete_own and not can_delete_any:
        existing = get_request("/fetchReview/" + str(review_id))
        if is_upstream_error(existing):
            return upstream_error_response(existing)
        record = existing if isinstance(existing, dict) else (existing[0] if existing else None)
        if not record:
            return api_error(404, "REVIEW_NOT_FOUND", "Review not found")
        if record.get("author_id") != user.id:
            return api_error(403, "FORBIDDEN", "You may only delete your own reviews")

    response = delete_request("/deleteReview/" + str(review_id))
    if is_upstream_error(response):
        return upstream_error_response(response)
    return JsonResponse({"status": 200, "message": "Review deleted"})
