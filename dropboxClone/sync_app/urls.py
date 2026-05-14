from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter(trailing_slash=True)
router.register("files", views.FileViewSet, basename="file")

urlpatterns = [
    path("", include(router.urls)),
    path("sync/changes", views.get_changes),
]
