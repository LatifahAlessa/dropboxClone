from django.utils import timezone
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ViewSet
from . import services
from .serializers import (
    FileSerializer,
    FileVersionSerializer,
    FileUploadSerializer,
    FileRenameSerializer,
    BulkFileUploadSerializer,
)
from .messages import ERROR_CONFLICT_DETECTED, FILE_NOT_FOUND, FILE_DELETE_SUCCESSFULLY
from .exceptions import (
    FileNotFoundException,
    VersionNotFoundException,
    FileContentNotFoundException,
    ConflictException,
)


class FileViewSet(ViewSet):

    def list(self, request):
        files = services.get_all_files(request.user)
        return Response(
            FileSerializer(files, many=True).data, status=status.HTTP_200_OK
        )

    def create(self, request):
        serializer = FileUploadSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        path = serializer.validated_data.get("path")
        name = serializer.validated_data.get("name")
        file_data = serializer.validated_data.get("file")
        client_version = int(request.headers.get("X-Client-Version", 0))

        try:
            file_obj = services.upload_file(
                user=request.user,
                path=path,
                name=name,
                file_data=file_data.read(),
                client_version=client_version,
            )
        except ConflictException:
            return Response(
                {"error": ERROR_CONFLICT_DETECTED}, status=status.HTTP_409_CONFLICT
            )

        return Response(FileSerializer(file_obj).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        try:
            file_obj = services.get_file(request.user, pk)
        except FileNotFoundException:
            return Response({"error": FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(FileSerializer(file_obj).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        version_num = request.query_params.get("version")

        try:
            download_url, file_hash = services.download_file(
                request.user, pk, version_num
            )
        except FileNotFoundException:
            return Response({"error": FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        except VersionNotFoundException:
            return Response(
                {"error": "version not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except FileContentNotFoundException:
            return Response(
                {"error": "file content not found"}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            {"download_url": download_url, "hash": file_hash}, status=status.HTTP_200_OK
        )

    def partial_update(self, request, pk=None):
        serializer = FileRenameSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_path = serializer.validated_data.get("new_path")
        new_name = serializer.validated_data.get("new_name")

        try:
            file_obj = services.rename_file(request.user, pk, new_path, new_name)
        except FileNotFoundException:
            return Response({"error": FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(FileSerializer(file_obj).data, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        try:
            services.delete_file(request.user, pk)
        except FileNotFoundException:
            return Response({"error": FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {"message": FILE_DELETE_SUCCESSFULLY}, status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        try:
            versions = services.get_file_history(request.user, pk)
        except FileNotFoundException:
            return Response({"error": FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            FileVersionSerializer(versions, many=True).data, status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        try:
            file_obj = services.restore_file(request.user, pk)
        except FileNotFoundException:
            return Response({"error": FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(FileSerializer(file_obj).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def bulk_upload(self, request):
        serializer = BulkFileUploadSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        files = serializer.validated_data.get("files")
        paths = serializer.validated_data.get("paths")
        client_version = int(request.headers.get("X-Client-Version", 0))

        results = services.bulk_upload_files(
            user=request.user,
            files=files,
            paths=paths,
            client_version=client_version,
        )

        response_data = [
            {
                "path": r["path"],
                "status": r["status"],
                "file": (
                    FileSerializer(r["file"]).data if r["status"] == "success" else None
                ),
                "detail": r.get("detail"),
            }
            for r in results
        ]

        return Response(response_data, status=status.HTTP_207_MULTI_STATUS)


@api_view(["GET"])
def get_changes(request):
    since = request.query_params.get("since")
    versions = services.get_changes(request.user, since)

    return Response(
        {
            "changes": FileVersionSerializer(versions, many=True).data,
            "last_sync": (
                versions.last().created_at if versions.exists() else timezone.now()
            ),
        },
        status=status.HTTP_200_OK,
    )
