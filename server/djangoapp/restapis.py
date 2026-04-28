import requests
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def require_env(name):
    value = os.getenv(name)
    if not value or str(value).strip() == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


backend_url = require_env("backend_url").rstrip("/")
sentiment_analyzer_url = require_env("sentiment_analyzer_url").rstrip("/")

# Maximum seconds to wait for any upstream service before giving up.
# Prevents Django threads from hanging when the DB or sentiment service is slow.
REQUEST_TIMEOUT = 10


def service_error(service, message, status=502, details=None):
    return {
        "ok": False,
        "status": status,
        "error": {
            "service": service,
            "message": message,
            "details": details,
        },
    }


def extract_response_details(response):
    if response is None:
        return None

    try:
        return response.json()
    except ValueError:
        return response.text


# Function to handle fetchReview and fetchDealers API requests
def get_request(endpoint, **kwargs):
    request_url = backend_url + endpoint

    print("GET from {} with params {}".format(request_url, kwargs or {}))
    try:
        # Call get method of requests library with URL and parameters
        response = requests.get(
            request_url,
            params=kwargs if kwargs else None,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as err:
        status = err.response.status_code if err.response is not None else 502
        return service_error(
            "database-api",
            "Backend API returned an error response.",
            status=status,
            details=extract_response_details(err.response),
        )
    except requests.exceptions.Timeout as err:
        return service_error(
            "database-api",
            "Request to backend API timed out.",
            status=504,
            details=str(err),
        )
    except requests.exceptions.RequestException as err:
        # If any network/connection error occurs
        return service_error(
            "database-api",
            "Request to backend API failed.",
            status=502,
            details=str(err),
        )


# Function to handle sentiment analyzer API request
def analyze_review_sentiments(text):
    request_url = sentiment_analyzer_url + "/analyze/" + text
    try:
        # Call get method of requests library with URL and parameters
        response = requests.get(request_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as err:
        status = err.response.status_code if err.response is not None else 502
        return service_error(
            "sentiment-analyzer",
            "Sentiment analyzer returned an error response.",
            status=status,
            details=extract_response_details(err.response),
        )
    except requests.exceptions.Timeout as err:
        return service_error(
            "sentiment-analyzer",
            "Sentiment analyzer request timed out.",
            status=504,
            details=str(err),
        )
    except requests.exceptions.RequestException as err:
        return service_error(
            "sentiment-analyzer",
            "Sentiment analyzer request failed.",
            status=502,
            details=str(err),
        )


# Function to handle PUT requests to the database API
def put_request(endpoint, data_dict):
    request_url = backend_url + endpoint
    print("PUT to {} with body {}".format(request_url, data_dict))
    try:
        response = requests.put(request_url, json=data_dict, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as err:
        status = err.response.status_code if err.response is not None else 502
        return service_error(
            "database-api",
            "Backend API returned an error response.",
            status=status,
            details=extract_response_details(err.response),
        )
    except requests.exceptions.Timeout as err:
        return service_error(
            "database-api",
            "Request to backend API timed out.",
            status=504,
            details=str(err),
        )
    except requests.exceptions.RequestException as err:
        return service_error(
            "database-api",
            "Request to backend API failed.",
            status=502,
            details=str(err),
        )


# Add review function
def post_review(data_dict):
    request_url = backend_url + "/insert_review"
    try:
        response = requests.post(request_url, json=data_dict, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        print(response.json())
        return response.json()
    except requests.exceptions.HTTPError as err:
        status = err.response.status_code if err.response is not None else 502
        return service_error(
            "database-api",
            "Backend API returned an error response while posting review.",
            status=status,
            details=extract_response_details(err.response),
        )
    except requests.exceptions.Timeout as err:
        return service_error(
            "database-api",
            "Review submission timed out.",
            status=504,
            details=str(err),
        )
    except requests.exceptions.RequestException as err:
        return service_error(
            "database-api",
            "Review submission failed.",
            status=502,
            details=str(err),
        )


# Function to handle DELETE requests to the database API
def delete_request(endpoint):
    request_url = backend_url + endpoint
    print("DELETE to {}".format(request_url))
    try:
        response = requests.delete(request_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as err:
        status = err.response.status_code if err.response is not None else 502
        return service_error(
            "database-api",
            "Backend API returned an error response.",
            status=status,
            details=extract_response_details(err.response),
        )
    except requests.exceptions.Timeout as err:
        return service_error(
            "database-api",
            "Request to backend API timed out.",
            status=504,
            details=str(err),
        )
    except requests.exceptions.RequestException as err:
        return service_error(
            "database-api",
            "Request to backend API failed.",
            status=502,
            details=str(err),
        )
