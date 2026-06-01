from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from sync_app import services
from sync_app.models import File, Folder
from sync_app.exceptions import FileNotFoundException, ConflictException
from .services import get_folder_context
from .forms import FileUploadForm, CreateFolderForm, RenameFileForm

User = get_user_model()

FILE_LIST_PARTIAL = "web/partials/file_list.html"


def register_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email", "")
        password = request.POST.get("password")
        if User.objects.filter(username=username).exists():
            return render(request, "web/register.html", {"error": "Username taken"})
        User.objects.create_user(username=username, email=email, password=password)
        return redirect("login")
    return render(request, "web/register.html")


@login_required
def files_view(request, folder_path=""):
    context = get_folder_context(request.user, folder_path)
    return render(request, "web/files.html", context)


@login_required
def upload_view(request):
    if request.method != "POST":
        return redirect("files")

    form = FileUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return redirect("files")

    file = form.cleaned_data["file"]
    current_path = form.cleaned_data["current_path"].strip()
    relative_path = request.POST.get("relative_path", "").strip()

    if relative_path:
        if current_path:
            path = f"/{current_path}/{relative_path}"
        else:
            path = f"/{relative_path}"
    elif current_path:
        path = f"/{current_path}/{file.name}"
    else:
        path = f"/{file.name}"

    try:
        services.upload_file(
            user=request.user,
            path=path,
            name=file.name,
            file_data=file.read(),
            client_version=0,
        )
    except ConflictException:
        pass

    context = get_folder_context(request.user, current_path)
    return render(request, FILE_LIST_PARTIAL, context)


@login_required
def create_folder_view(request):
    if request.method != "POST":
        return redirect("files")

    form = CreateFolderForm(request.POST)
    if not form.is_valid():
        return redirect("files")

    folder_name = form.cleaned_data["folder_name"].strip()
    current_path = form.cleaned_data["current_path"].strip()

    parent = Folder.objects.resolve_path(request.user, current_path)
    services.create_folder(request.user, folder_name, parent)

    context = get_folder_context(request.user, current_path)
    return render(request, FILE_LIST_PARTIAL, context)


@login_required
def delete_view(request, file_id):
    try:
        services.delete_file(request.user, file_id)
    except FileNotFoundException:
        pass

    current_path = request.POST.get("current_path", "").strip()
    context = get_folder_context(request.user, current_path)
    return render(request, FILE_LIST_PARTIAL, context)


@login_required
def rename_view(request, file_id):
    if request.method != "POST":
        return redirect("files")

    form = RenameFileForm(request.POST)
    current_path = request.POST.get("current_path", "").strip()

    if not form.is_valid():
        context = get_folder_context(request.user, current_path)
        return render(request, FILE_LIST_PARTIAL, context)

    new_name = form.cleaned_data["new_name"].strip()
    current_path = form.cleaned_data["current_path"].strip()

    try:
        file_obj = services.get_file(request.user, file_id)
        path_parts = file_obj.path.rsplit("/", 1)
        new_path = (
            f"{path_parts[0]}/{new_name}" if len(path_parts) > 1 else f"/{new_name}"
        )
        services.rename_file(request.user, file_id, new_path, new_name)
    except FileNotFoundException:
        pass

    context = get_folder_context(request.user, current_path)
    return render(request, FILE_LIST_PARTIAL, context)


@login_required
def download_view(request, file_id):
    try:
        download_url, _ = services.download_file(request.user, file_id)
    except FileNotFoundException:
        return redirect("files")

    return redirect(download_url)


@login_required
def trash_view(request):
    files = File.objects.deleted_for_user(request.user)
    return render(request, "web/trash.html", {"files": files})


@login_required
def restore_view(request, file_id):
    try:
        services.restore_file(request.user, file_id)
    except FileNotFoundException:
        pass

    files = File.objects.deleted_for_user(request.user)
    return render(request, "web/partials/trash_list.html", {"files": files})


@login_required
def history_view(request, file_id):
    try:
        file_obj = services.get_file(request.user, file_id)
        versions = services.get_file_history(request.user, file_id)
    except FileNotFoundException:
        return redirect("files")

    return render(request, "web/history.html", {"file": file_obj, "versions": versions})
