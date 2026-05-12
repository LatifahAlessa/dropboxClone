from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ViewSet
from . import services
from .serializers import FileSerializer, FileVersionSerializer, FileUploadSerializer, FileRenameSerializer
from .messages import ERROR_CONFLICT_DETECTED, FILE_NOT_FOUND, FILE_DELETE_SUCCESSFULLY


class FileViewSet(ViewSet):
    """
    list:    GET    /api/files/
    create:  POST   /api/files/
    retrieve: GET   /api/files/<id>/
    partial_update: PATCH /api/files/<id>/
    destroy: DELETE /api/files/<id>/
    download: GET   /api/files/<id>/download/
    history: GET    /api/files/<id>/history/
    restore: POST   /api/files/<id>/restore/
    """

    def list(self, request):
        files = services.get_all_files(request.user)
        return Response(
            FileSerializer(files, many=True).data,
            status=status.HTTP_200_OK
        )

    def create(self, request):
        serializer = FileUploadSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        path = serializer.validated_data.get('path')
        name = serializer.validated_data.get('name')
        file_data = serializer.validated_data.get('file')
        client_version = int(request.headers.get('X-Client-Version', 0))

        file_obj, result = services.upload_file(
            user=request.user,
            path=path,
            name=name,
            file_data=file_data.read(),
            client_version=client_version
        )

        if result == 'conflict':
            return Response({'error': ERROR_CONFLICT_DETECTED}, status=status.HTTP_409_CONFLICT)

        return Response(FileSerializer(file_obj).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        file_obj = services.get_file(request.user, pk)

        if not file_obj:
            return Response({'error': FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(FileSerializer(file_obj).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        version_num = request.query_params.get('version')
        file_obj, version, file_data, result = services.download_file(request.user, pk, version_num)

        if result == 'not_found':
            return Response({'error': FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        if result == 'version_not_found':
            return Response({'error': 'version not found'}, status=status.HTTP_404_NOT_FOUND)
        if result == 'file_not_found':
            return Response({'error': 'file content not found'}, status=status.HTTP_404_NOT_FOUND)

        return HttpResponse(
            file_data,
            content_type='application/octet-stream',
            headers={'Content-Disposition': f'attachment; filename="{file_obj.name}"'}
        )

    def partial_update(self, request, pk=None):
        serializer = FileRenameSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        new_path = serializer.validated_data.get('new_path')
        new_name = serializer.validated_data.get('new_name')

        file_obj, result = services.rename_file(request.user, pk, new_path, new_name)

        if result == 'not_found':
            return Response({'error': FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(FileSerializer(file_obj).data, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        file_obj, result = services.delete_file(request.user, pk)

        if result == 'not_found':
            return Response({'error': FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response({'message': FILE_DELETE_SUCCESSFULLY}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        versions, result = services.get_file_history(request.user, pk)

        if result == 'not_found':
            return Response({'error': FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(FileVersionSerializer(versions, many=True).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        file_obj, result = services.restore_file(request.user, pk)

        if result == 'not_found':
            return Response({'error': FILE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(FileSerializer(file_obj).data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_changes(request):
    since = request.query_params.get('since')
    versions = services.get_changes(since)

    return Response({
        'changes': FileVersionSerializer(versions, many=True).data,
        'last_sync': versions.last().created_at if versions.exists() else timezone.now()
    }, status=status.HTTP_200_OK)
