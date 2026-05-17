from django.db import models
from django.conf import settings
from .constants import OPERATION_CHOICES
from .manager import FileManager, FileVersionManager
from uuid_extensions import uuid7


class File(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="files"
    )
    path = models.CharField(max_length=500)
    name = models.CharField(max_length=255)
    is_deleted = models.BooleanField(default=False)
    current_version = models.IntegerField(default=1)
    last_modified_time = models.DateTimeField(auto_now=True)
    objects = FileManager()

    class Meta:
        unique_together = ("user", "path")

    def __str__(self):
        return self.path


class FileVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    file = models.ForeignKey("File", on_delete=models.CASCADE, related_name="versions")
    version_num = models.IntegerField()
    operation_type = models.CharField(max_length=20, choices=OPERATION_CHOICES)
    hash = models.CharField(max_length=128, blank=True, null=True)
    size = models.BigIntegerField(default=0)
    storage_path = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = FileVersionManager()

    def __str__(self):
        return f"{self.file.path} v{self.version_num}"
