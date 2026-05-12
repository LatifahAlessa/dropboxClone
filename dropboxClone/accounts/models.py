from django.db import models
from django.contrib.auth.models import AbstractUser
from uuid_extensions import uuid7


def generate_uuid():
    return uuid7()


class CustomUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
