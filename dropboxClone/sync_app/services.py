from .models import File, FileVersion, Folder
import hashlib
from django.db import IntegrityError
from django.db.models import QuerySet
from . import storage
from concurrent.futures import ThreadPoolExecutor, as_completed
from .exceptions import (
    FileNotFoundException,
    VersionNotFoundException,
    FileContentNotFoundException,
    ConflictException,
)


def create_folder_path(user, path):
    parts = path.strip("/").split("/")
    if len(parts) <= 1:
        return None

    folder_names = parts[:-1]
    parent = None

    for name in folder_names:
        try:
            folder, _ = Folder.objects.get_or_create(
                user=user, parent=parent, name=name
            )
        except IntegrityError:
            folder = Folder.objects.get(user=user, parent=parent, name=name)
        parent = folder

    return parent


# UPLOAD
def upload_file(user, path, name, file_data, client_version) -> File:
    folder = create_folder_path(user, path)

    file_obj, created = File.objects.get_or_create(
        user=user, path=path, defaults={"name": name, "folder": folder}
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


# Bulk Upload
def bulk_upload_files(user, files, paths, client_version) -> list:
    def upload_single(file, path):
        name = file.name
        file_data = file.read()
        return upload_file(user, path, name, file_data, client_version)

    tasks = zip(files, paths)
    results = []

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(upload_single, file, path): path for file, path in tasks
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                file_obj = future.result()
                results.append(
                    {
                        "path": path,
                        "status": "success",
                        "file": file_obj,
                    }
                )
            except ConflictException:
                results.append(
                    {
                        "path": path,
                        "status": "conflict",
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "path": path,
                        "status": "error",
                        "detail": str(e),
                    }
                )

    return results


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

    new_folder = create_folder_path(user, new_path)
    file_obj.path = new_path
    file_obj.name = new_name
    file_obj.folder = new_folder
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


def create_folder(user, name, parent=None) -> Folder:
    folder, _ = Folder.objects.get_or_create(user=user, parent=parent, name=name)
    return folder


def get_folder(user, folder_id) -> Folder:
    try:
        return Folder.objects.for_user(user).get(id=folder_id)
    except Folder.DoesNotExist:
        raise FileNotFoundException()


def get_subfolders(user, parent=None) -> QuerySet:
    return Folder.objects.children_of(user, parent)


def get_files_in_folder(user, folder=None) -> QuerySet:
    return File.objects.in_folder(user, folder)
