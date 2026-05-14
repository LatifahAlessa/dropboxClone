from django.db import models


class FileManager(models.Manager):
    def for_user(self, user):
        return self.filter(user_id=user.id)

    def active_for_user(self, user):
        return self.filter(user_id=user.id, is_deleted=False)

    def deleted_for_user(self, user):
        return self.filter(user_id=user.id, is_deleted=True)


class FileVersionManager(models.Manager):
    def for_file(self, file_obj):
        return self.filter(file=file_obj).order_by("-version_num")

    def content_versions(self, file_obj):
        return self.filter(file=file_obj, operation_type__in=["CREATE", "MODIFY"])

    def for_user(self, user):
        return (
            self.filter(file__user_id=user.id)
            .select_related("file")
            .order_by("created_at")
        )
