from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="web/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("register/", views.register_view, name="register"),
    path("", views.files_view, name="files"),
    path("folder/<path:folder_path>/", views.files_view, name="files_folder"),
    path("upload/", views.upload_view, name="upload"),
    path("create-folder/", views.create_folder_view, name="create_folder"),
    path("delete/<uuid:file_id>/", views.delete_view, name="delete"),
    path("rename/<uuid:file_id>/", views.rename_view, name="rename"),
    path("download/<uuid:file_id>/", views.download_view, name="download"),
    path("trash/", views.trash_view, name="trash"),
    path("restore/<uuid:file_id>/", views.restore_view, name="restore"),
    path("history/<uuid:file_id>/", views.history_view, name="history"),
]
