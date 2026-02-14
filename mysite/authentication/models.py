from django.db import models
from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_EDITOR = "editor"
    ROLE_VIEWER = "viewer"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_EDITOR, "Editor"),
        (ROLE_VIEWER, "Viewer"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)

