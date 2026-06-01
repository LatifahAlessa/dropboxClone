from sync_app import services
from sync_app import storage
from sync_app.models import Folder


def get_folder_context(user, folder_path):
    folder = Folder.objects.resolve_path(user, folder_path)

    subfolders = services.get_subfolders(user, folder)
    files = services.get_files_in_folder(user, folder)

    files_with_thumbnails = []
    for file in files:
        thumbnail_url = None
        if file.thumbnail_path:
            thumbnail_url = storage.get_presigned_url(file.thumbnail_path)
        files_with_thumbnails.append({"file": file, "thumbnail_url": thumbnail_url})

    breadcrumbs = []
    current = folder
    while current:
        breadcrumbs.append(
            {
                "name": current.name,
                "path": current.get_full_path().strip("/"),
            }
        )
        current = current.parent
    breadcrumbs.reverse()

    return {
        "files": files_with_thumbnails,
        "subfolders": subfolders,
        "current_path": folder_path.strip("/") if folder_path else "",
        "current_folder": folder,
        "breadcrumbs": breadcrumbs,
    }
