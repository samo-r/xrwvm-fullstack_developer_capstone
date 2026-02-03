from django.contrib import admin
from .models import CarMake, CarModel


# Register your models here.

from django.contrib import admin
from .models import CarMake, CarModel

# For the intergrated view on the carmake page
class CarModelInline(admin.TabularInline):
    model = CarModel
    extra = 1 

@admin.register(CarMake)
class CarMakeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    inlines = [CarModelInline]

# Car model view 
@admin.register(CarModel)
class CarModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'car_make', 'year', 'type')
    list_filter = ['car_make', 'type'] # Filter
    search_fields = ['name']

# Register models here
