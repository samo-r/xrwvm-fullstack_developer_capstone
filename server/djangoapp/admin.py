# Register your models here.

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import CarMake, CarModel, User


# Custom admin panel for the User model.
# Extends Django's built-in UserAdmin to show and manage role/dealer fields.
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Show role and dealer ID columns in the user list view.
    list_display = ("username", "email", "role", "assigned_dealer_id", "is_staff")
    # Allow filtering users by role in the sidebar.
    list_filter = BaseUserAdmin.list_filter + ("role",)

    # Add Business Access section to the user edit form.
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Business Access",
            {"fields": ("role", "assigned_dealer_id")},
        ),
    )

    # Add Business Access section to the user creation form.
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "Business Access",
            {
                "classes": ("wide",),
                "fields": ("role", "assigned_dealer_id"),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        # Only superusers can elevate a user to DEALER_ADMIN or assign a dealer.
        # If a non-superuser staff member attempts this, silently force CUSTOMER.
        if not request.user.is_superuser:
            obj.role = User.Roles.CUSTOMER
            obj.assigned_dealer_id = None

        super().save_model(request, obj, form, change)


# For the intergrated view on the carmake page
class CarModelInline(admin.TabularInline):
    model = CarModel
    extra = 1


@admin.register(CarMake)
class CarMakeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    inlines = [CarModelInline]


# Car model view
@admin.register(CarModel)
class CarModelAdmin(admin.ModelAdmin):
    list_display = ("name", "car_make", "year", "type")
    list_filter = ["car_make", "type"]  # Filter
    search_fields = ["name"]


# Register models here
