from django.db import models

class Province(models.TextChoices):
    KOSHI = "01", "Koshi Province"
    MADHESH = "02", "Madhesh Province"
    BAGMATI = "03", "Bagmati Province"
    GANDAKI = "04", "Gandaki Province"
    LUMBINI = "05", "Lumbini Province"
    KARNALI = "06", "Karnali Province"
    SUDURPASCHIM = "07", "Sudurpaschim Province"