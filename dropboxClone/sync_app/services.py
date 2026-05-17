from .models import File, FileVersion
import hashlib
from django.db.models import QuerySet
from . import storage
from .exceptions import (
    FileNotFoundException,
    VersionNotFoundException,
    FileContentNotFoundException,
    ConflictException,
)


# UPLOAD
def upload_file(user, path, name, file_data, client_version) -> File:
    file_obj, created = File.objects.get_or_create(
        user=user, path=path, defaults={"name": name}
    )

    if not created and client_version != file_obj.current_version:
        raise ConflictException()

    file_hash = hashlib.md5(file_data).hexdigest()

    latest_version = (
        FileVersion.objects.content_versions(file_obj).order_by("-version_num").first()
    )
    if latest_version and latest_version.hash == file_hash:
        return file_obj

    new_version = file_obj.current_version + 1 if not created else 1
    storage_key = f"users/{user.id}/v{new_version}/{path.lstrip('/')}"

    storage.upload_to_storage(file_data, storage_key)

    FileVersion.objects.create(
        file=file_obj,
        version_num=new_version,
        operation_type="CREATE" if created else "MODIFY",
        hash=file_hash,
        size=len(file_data),
        storage_path=storage_key,
    )

    file_obj.current_version = new_version
    file_obj.name = name
    file_obj.save()

    old_versions = FileVersion.objects.for_file(file_obj)[5:]

    for version in old_versions:
        if version.storage_path:
            storage.delete_from_storage(version.storage_path)
        version.delete()

    return file_obj


# DELETE
def delete_file(user, file_id) -> File:
    try:
        file_obj = File.objects.active_for_user(user).get(id=file_id)
    except File.DoesNotExist:
        raise FileNotFoundException()

    file_obj.is_deleted = True
    file_obj.save()

    FileVersion.objects.create(
        file=file_obj,
        version_num=file_obj.current_version,
        operation_type="DELETE",
        size=0,
    )

    versions = FileVersion.objects.content_versions(file_obj)
    for version in versions:
        if version.storage_path:
            trash_key = f"trash/{version.storage_path}"
            storage.move_to_trash(version.storage_path, trash_key)
            version.storage_path = trash_key
            version.save()

    return file_obj


# RENAME
def rename_file(user, file_id, new_path, new_name) -> File:
    try:
        file_obj = File.objects.active_for_user(user).get(id=file_id)
    except File.DoesNotExist:
        raise FileNotFoundException()

    latest_version = (
        FileVersion.objects.content_versions(file_obj).order_by("-version_num").first()
    )

    if latest_version and latest_version.storage_path:
        new_storage_key = latest_version.storage_path.replace(
            file_obj.path.lstrip("/"), new_path.lstrip("/")
        )
        storage.rename_in_storage(latest_version.storage_path, new_storage_key)
        latest_version.storage_path = new_storage_key
        latest_version.save()

    FileVersion.objects.create(
        file=file_obj,
        version_num=file_obj.current_version,
        operation_type="RENAME",
        size=0,
    )

    file_obj.path = new_path
    file_obj.name = new_name
    file_obj.save()

    return file_obj


# GET HISTORY
def get_file_history(user, file_id) -> QuerySet:
    try:
        file_obj = File.objects.for_user(user).get(id=file_id)
    except File.DoesNotExist:
        raise FileNotFoundException()

    return FileVersion.objects.for_file(file_obj)


# GET CHANGES
def get_changes(user, since_timestamp) -> QuerySet:
    versions = FileVersion.objects.for_user(user)
    if since_timestamp:
        versions = versions.filter(created_at__gt=since_timestamp)
    return versions


# DOWNLOAD
def download_file(user, file_id, version_num=None) -> tuple[str, str]:
    try:
        file_obj = File.objects.for_user(user).get(id=file_id)
    except File.DoesNotExist:
        raise FileNotFoundException()

    if version_num:
        try:
            version = FileVersion.objects.content_versions(file_obj).get(
                version_num=version_num
            )
        except FileVersion.DoesNotExist:
            raise VersionNotFoundException()
    else:
        version = (
            FileVersion.objects.content_versions(file_obj)
            .order_by("-version_num")
            .first()
        )

        if not version or not version.storage_path:
            raise FileContentNotFoundException()

    return storage.get_presigned_url(version.storage_path), version.hash


# GET ALL FILES
def get_all_files(user) -> QuerySet:
    return File.objects.active_for_user(user)


# GET SINGLE FILE
def get_file(user, file_id) -> File:
    try:
        return File.objects.active_for_user(user).get(id=file_id)
    except File.DoesNotExist:
        raise FileNotFoundException()


# RESTORE
def restore_file(user, file_id) -> File:
    try:
        file_obj = File.objects.deleted_for_user(user).get(id=file_id)
    except File.DoesNotExist:
        raise FileNotFoundException()

    versions = FileVersion.objects.content_versions(file_obj)
    for version in versions:
        if version.storage_path and version.storage_path.startswith("trash/"):
            original_key = version.storage_path.replace("trash/", "", 1)
            storage.restore_from_trash(version.storage_path, original_key)
            version.storage_path = original_key
            version.save()

    file_obj.is_deleted = False
    file_obj.save()

    FileVersion.objects.create(
        file=file_obj,
        version_num=file_obj.current_version,
        operation_type="RESTORE",
        size=0,
    )

    return file_obj
