from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from sync_app import services
from sync_app.models import File
from sync_app.exceptions import FileNotFoundException, ConflictException

User = get_user_model()


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("files")
        return render(request, "web/login.html", {"error": "Invalid credentials"})
    return render(request, "web/login.html")


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


def logout_view(request):
    logout(request)
    return redirect("login")


def _get_folder_context(user, current_path):
    current_path = current_path.strip("/")
    all_files = services.get_all_files(user)

    prefix = f"/{current_path}/" if current_path else "/"

    files_here = []
    subfolder_names = set()

    for f in all_files:
        if not f.path.startswith(prefix):
            continue

        relative = f.path[len(prefix):]

        if "/" in relative:
            subfolder_names.add(relative.split("/")[0])
        else:
            files_here.append(f)

    breadcrumbs = []
    if current_path:
        parts = current_path.split("/")
        for i, part in enumerate(parts):
            breadcrumbs.append({
                "name": part,
                "path": "/".join(parts[: i + 1]),
            })

    return {
        "files": files_here,
        "subfolders": sorted(subfolder_names),
        "current_path": current_path,
        "breadcrumbs": breadcrumbs,
    }


@login_required(login_url="/login/")
def files_view(request, folder_path=""):
    context = _get_folder_context(request.user, folder_path)
    return render(request, "web/files.html", context)


@login_required(login_url="/login/")
def upload_view(request):
    if request.method != "POST":
        return redirect("files")

    file = request.FILES.get("file")
    if not file:
        return redirect("files")

    current_path = request.POST.get("current_path", "").strip()

    if current_path:
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

    context = _get_folder_context(request.user, current_path)
    return render(request, "web/partials/file_list.html", context)


@login_required(login_url="/login/")
def create_folder_view(request):
    if request.method != "POST":
        return redirect("files")

    folder_name = request.POST.get("folder_name", "").strip()
    current_path = request.POST.get("current_path", "").strip()

    if not folder_name:
        return redirect("files")

    if current_path:
        path = f"/{current_path}/{folder_name}/.keep"
    else:
        path = f"/{folder_name}/.keep"

    try:
        services.upload_file(
            user=request.user,
            path=path,
            name=".keep",
            file_data=b"",
            client_version=0,
        )
    except ConflictException:
        pass

    context = _get_folder_context(request.user, current_path)
    return render(request, "web/partials/file_list.html", context)


@login_required(login_url="/login/")
def delete_view(request, file_id):
    try:
        services.delete_file(request.user, file_id)
    except FileNotFoundException:
        pass

    current_path = request.POST.get("current_path", "").strip()
    context = _get_folder_context(request.user, current_path)
    return render(request, "web/partials/file_list.html", context)


@login_required(login_url="/login/")
def rename_view(request, file_id):
    if request.method != "POST":
        return redirect("files")

    new_name = request.POST.get("new_name", "").strip()
    current_path = request.POST.get("current_path", "").strip()

    if not new_name:
        context = _get_folder_context(request.user, current_path)
        return render(request, "web/partials/file_list.html", context)

    try:
        file_obj = services.get_file(request.user, file_id)
        path_parts = file_obj.path.rsplit("/", 1)
        new_path = (
            f"{path_parts[0]}/{new_name}" if len(path_parts) > 1 else f"/{new_name}"
        )
        services.rename_file(request.user, file_id, new_path, new_name)
    except FileNotFoundException:
        pass

    context = _get_folder_context(request.user, current_path)
    return render(request, "web/partials/file_list.html", context)


@login_required(login_url="/login/")
def download_view(request, file_id):
    try:
        download_url, _ = services.download_file(request.user, file_id)
    except FileNotFoundException:
        return redirect("files")

    return redirect(download_url)


@login_required(login_url="/login/")
def trash_view(request):
    files = File.objects.deleted_for_user(request.user)
    return render(request, "web/trash.html", {"files": files})


@login_required(login_url="/login/")
def restore_view(request, file_id):
    try:
        services.restore_file(request.user, file_id)
    except FileNotFoundException:
        pass

    files = File.objects.deleted_for_user(request.user)
    return render(request, "web/partials/trash_list.html", {"files": files})


@login_required(login_url="/login/")
def history_view(request, file_id):
    try:
        file_obj = services.get_file(request.user, file_id)
        versions = services.get_file_history(request.user, file_id)
    except FileNotFoundException:
        return redirect("files")

    return render(
        request, "web/history.html", {"file": file_obj, "versions": versions}
    )
