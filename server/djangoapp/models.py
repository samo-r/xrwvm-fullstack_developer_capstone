from django.db import models
from django.utils.timezone import now
from django.core.validators import MaxValueValidator, MinValueValidator
import datetime

# Get current year
def current_year():
    return datetime.date.today().year

# Create your models here.

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
        ('SEDAN', 'Sedan'),
        ('SUV', 'SUV'),
        ('WAGON', 'Wagon'),
        ('PICKUP', 'Pickup'),
        ('COUPE', 'Coupe'),
        ('VAN','Van'),
        ('MINIVAN', 'Minivan'),
        ('CONVERTIBLE', 'Convertible'),
        ('HATCHBACK', 'Hatchback')
    ]
    type = models.CharField(max_length=50, choices=CAR_TYPES, default='SUV')
    
    year = models.IntegerField(
        default=current_year,
        validators=[
            MaxValueValidator(current_year),
            MinValueValidator(2010),
        ])

    def __str__(self):
        return self.name