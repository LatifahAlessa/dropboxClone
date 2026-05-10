from .models import File, FileVersion
import hashlib
from . import storage


# UPLOAD
def upload_file(path, name, file_data, client_version):
    file_obj, created = File.objects.get_or_create(
        path=path,
        defaults={'name': name}
    )

    if not created and client_version != file_obj.current_version:
        return None, 'conflict'

    file_hash = hashlib.md5(file_data).hexdigest()
    new_version = file_obj.current_version + 1 if not created else 1
    storage_key = f"v{new_version}/{path.lstrip('/')}"

    storage.upload_to_minio(file_data, storage_key)

    FileVersion.objects.create(
        file=file_obj,
        version_num=new_version,
        operation_type='CREATE' if created else 'MODIFY',
        hash=file_hash,
        size=len(file_data),
        storage_path=storage_key
    )

    file_obj.current_version = new_version
    file_obj.name = name
    file_obj.save()

    old_versions = FileVersion.objects.filter(
        file=file_obj
    ).order_by('-version_num')[5:]

    for version in old_versions:
        if version.storage_path:
            storage.delete_from_minio(version.storage_path)
        version.delete()

    return file_obj, 'created' if created else 'updated'


# DELETE
def delete_file(file_id):
    try:
        file_obj = File.objects.get(id=file_id, is_deleted=False)
    except File.DoesNotExist:
        return None, 'not_found'

    file_obj.is_deleted = True
    file_obj.save()

    FileVersion.objects.create(
        file=file_obj,
        version_num=file_obj.current_version,
        operation_type='DELETE',
        size=0,
    )

    versions = FileVersion.objects.filter(
        file=file_obj,
        operation_type__in=['CREATE', 'MODIFY']
    )
    for version in versions:
        if version.storage_path:
            trash_key = f"trash/{version.storage_path}"
            storage.move_to_trash(version.storage_path, trash_key)
            version.storage_path = trash_key
            version.save()

    return file_obj, 'deleted'


# RENAME
def rename_file(file_id, new_path, new_name):
    try:
        file_obj = File.objects.get(id=file_id, is_deleted=False)
    except File.DoesNotExist:
        return None, 'not_found'

    latest_version = FileVersion.objects.filter(
        file=file_obj,
        operation_type__in=['CREATE', 'MODIFY']
    ).order_by('-version_num').first()

    if latest_version and latest_version.storage_path:
        new_storage_key = latest_version.storage_path.replace(
            file_obj.path.lstrip('/'),
            new_path.lstrip('/')
        )
        storage.rename_in_minio(latest_version.storage_path, new_storage_key)
        latest_version.storage_path = new_storage_key
        latest_version.save()

    FileVersion.objects.create(
        file=file_obj,
        version_num=file_obj.current_version,
        operation_type='RENAME',
        size=0,
    )

    file_obj.path = new_path
    file_obj.name = new_name
    file_obj.save()

    return file_obj, 'renamed'


# GET HISTORY
def get_file_history(file_id):
    try:
        file_obj = File.objects.get(id=file_id)
    except File.DoesNotExist:
        return None, 'not_found'

    versions = FileVersion.objects.filter(
        file=file_obj
    ).order_by('-version_num')

    return versions, 'ok'


# GET CHANGES
def get_changes(since_timestamp):
    versions = FileVersion.objects.filter(
        created_at__gt=since_timestamp
    ).select_related('file').order_by('created_at')
    return versions


# DOWNLOAD
def download_file(file_id, version_num=None):
    try:
        file_obj = File.objects.get(id=file_id)
    except File.DoesNotExist:
        return None, None, None, 'not_found'

    if version_num:
        try:
            version = FileVersion.objects.get(
                file=file_obj,
                version_num=version_num,
                operation_type__in=['CREATE', 'MODIFY']
            )
        except FileVersion.DoesNotExist:
            return None, None, None, 'version_not_found'
    else:
        version = FileVersion.objects.filter(
            file=file_obj,
            operation_type__in=['CREATE', 'MODIFY']
        ).order_by('-version_num').first()

    if not version or not version.storage_path:
        return None, None, None, 'file_not_found'

    file_data = storage.download_from_minio(version.storage_path)

    return file_obj, version, file_data, 'ok'


# GET ALL FILES
def get_all_files():
    files = File.objects.filter(is_deleted=False)
    return files


# GET SINGLE FILE
def get_file(file_id):
    try:
        return File.objects.get(id=file_id, is_deleted=False)
    except File.DoesNotExist:
        return None


# RESTORE
def restore_file(file_id):
    try:
        file_obj = File.objects.get(id=file_id, is_deleted=True)
    except File.DoesNotExist:
        return None, 'not_found'

    versions = FileVersion.objects.filter(
        file=file_obj,
        operation_type__in=['CREATE', 'MODIFY']
    )
    for version in versions:
        if version.storage_path and version.storage_path.startswith('trash/'):
            original_key = version.storage_path.replace('trash/', '', 1)
            storage.restore_from_trash(version.storage_path, original_key)
            version.storage_path = original_key
            version.save()

    file_obj.is_deleted = False
    file_obj.save()

    FileVersion.objects.create(
        file=file_obj,
        version_num=file_obj.current_version,
        operation_type='RESTORE',
        size=0,
    )

    return file_obj, 'restored'