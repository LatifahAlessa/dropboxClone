from rest_framework import serializers
from .models import File, FileVersion

class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ['id', 'path', 'name', 'current_version', 'last_modified_time']

class FileVersionSerializer(serializers.ModelSerializer):
    file_path = serializers.CharField(source='file.path', read_only=True)
    file_name = serializers.CharField(source='file.name', read_only=True)

    class Meta:
        model = FileVersion
        fields = ['id', 'file', 'file_path', 'file_name', 'version_num', 'operation_type', 'hash', 'size', 'created_at', 'storage_path']


class FileUploadSerializer(serializers.Serializer):
    path = serializers.CharField(max_length=500)
    name = serializers.CharField(max_length=255)
    file = serializers.FileField()


class FileRenameSerializer(serializers.Serializer):
    new_path = serializers.CharField(max_length=500)
    new_name = serializers.CharField(max_length=255)