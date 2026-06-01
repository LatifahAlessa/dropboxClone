from django.db import models


class FolderManager(models.Manager):
    def for_user(self, user):
        return self.filter(user_id=user.id)

    def root_folders(self, user):
        return self.filter(user_id=user.id, parent=None)

    def children_of(self, user, parent):
        return self.filter(user_id=user.id, parent=parent)

    def resolve_path(self, user, folder_path):
        if not folder_path:
            return None
        parent = None
        for name in folder_path.strip("/").split("/"):
            try:
                parent = self.get(user=user, parent=parent, name=name)
            except self.model.DoesNotExist:
                return None
        return parent


class FileManager(models.Manager):
    def for_user(self, user):
        return self.filter(user_id=user.id)

    def active_for_user(self, user):
        return self.filter(user_id=user.id, is_deleted=False)

    def deleted_for_user(self, user):
        return self.filter(user_id=user.id, is_deleted=True)

    def in_folder(self, user, folder):
        return self.filter(user_id=user.id, folder=folder, is_deleted=False)


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
