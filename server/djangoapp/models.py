from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
import datetime


# Get current year
def current_year():
    return datetime.date.today().year

# Create your models here.

class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Ensure superusers always carry ADMIN role at creation time.
        extra_fields["role"] = "ADMIN"
        # Superusers should not be linked to a dealership.
        extra_fields["assigned_dealer_id"] = None
        return super().create_superuser(username, email, password, **extra_fields)


# Custom user model extending Django's built-in AbstractUser.
# This replaces the default auth.User and must be set as AUTH_USER_MODEL in settings.
class User(AbstractUser):
    # Three business roles that control what each user can do in the platform.
    class Roles(models.TextChoices):
        ADMIN = "ADMIN", "System Admin"          
        DEALER_ADMIN = "DEALER_ADMIN", "Dealer Admin" 
        CUSTOMER = "CUSTOMER", "Customer"       

    # Every user has exactly one role. Defaults to CUSTOMER for public signups.
    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        default=Roles.CUSTOMER,
    )

    # Links a DEALER_ADMIN to their specific dealership in the Node database.
    # Null for ADMIN and CUSTOMER roles.
    assigned_dealer_id = models.PositiveIntegerField(null=True, blank=True)

    objects = UserManager()

    def clean(self):
        """Enforce business rules on role and dealer assignment before saving."""
        super().clean()

        # Django superusers bypass role checks and are always treated as ADMIN.
        if self.is_superuser:
            self.role = self.Roles.ADMIN

        # A DEALER_ADMIN without a dealer assignment is invalid.
        if self.role == self.Roles.DEALER_ADMIN and not self.assigned_dealer_id:
            raise ValidationError(
                {"assigned_dealer_id": "Dealer Admin must have an assigned dealer ID."}
            )

        # Non-dealer-admin roles must never hold a dealer assignment.
        if self.role != self.Roles.DEALER_ADMIN:
            self.assigned_dealer_id = None


# Car make model
class CarMake(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.name


# Car Model model
class CarModel(models.Model):
    car_make = models.ForeignKey(CarMake, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    CAR_TYPES = [
        ("SEDAN", "Sedan"),
        ("SUV", "SUV"),
        ("WAGON", "Wagon"),
        ("PICKUP", "Pickup"),
        ("COUPE", "Coupe"),
        ("VAN", "Van"),
        ("MINIVAN", "Minivan"),
        ("CONVERTIBLE", "Convertible"),
        ("HATCHBACK", "Hatchback"),
    ]
    type = models.CharField(max_length=50, choices=CAR_TYPES, default="SUV")

    year = models.IntegerField(
        default=current_year,
        validators=[
            MaxValueValidator(current_year),
            MinValueValidator(2010),
        ],
    )

    def __str__(self):
        return self.name
