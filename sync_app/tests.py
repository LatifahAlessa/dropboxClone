import uuid
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, call
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import File, FileVersion


class UploadFileTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('sync_app.storage.upload_to_minio')
    def test_upload_new_file(self, mock_upload):
        file = SimpleUploadedFile('test.txt', b'hello world', content_type='text/plain')
        response = self.client.post(
            '/api/files/',
            data={'path': '/desktop/test.txt', 'name': 'test.txt', 'file': file},
            HTTP_X_CLIENT_VERSION='0',
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['path'], '/desktop/test.txt')
        self.assertEqual(response.data['current_version'], 1)
        mock_upload.assert_called_once()

    @patch('sync_app.storage.upload_to_minio')
    def test_upload_creates_file_version(self, mock_upload):
        file = SimpleUploadedFile('test.txt', b'hello world', content_type='text/plain')
        self.client.post(
            '/api/files/',
            data={'path': '/desktop/test.txt', 'name': 'test.txt', 'file': file},
            HTTP_X_CLIENT_VERSION='0',
            format='multipart'
        )
        self.assertEqual(FileVersion.objects.count(), 1)
        version = FileVersion.objects.first()
        self.assertEqual(version.operation_type, 'CREATE')
        self.assertEqual(version.version_num, 1)
        self.assertGreater(version.size, 0)

    @patch('sync_app.storage.upload_to_minio')
    def test_upload_modify_existing_file(self, mock_upload):
        file_obj = File.objects.create(path='/desktop/test.txt', name='test.txt', current_version=1)
        FileVersion.objects.create(
            file=file_obj, version_num=1, operation_type='CREATE',
            size=11, storage_path='v1/desktop/test.txt'
        )

        file = SimpleUploadedFile('test.txt', b'updated content', content_type='text/plain')
        response = self.client.post(
            '/api/files/',
            data={'path': '/desktop/test.txt', 'name': 'test.txt', 'file': file},
            HTTP_X_CLIENT_VERSION='1',
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['current_version'], 2)

        version = FileVersion.objects.filter(file=file_obj).order_by('-version_num').first()
        self.assertEqual(version.operation_type, 'MODIFY')
        self.assertEqual(version.version_num, 2)

    @patch('sync_app.storage.upload_to_minio')
    def test_upload_conflict(self, mock_upload):
        File.objects.create(path='/desktop/test.txt', name='test.txt', current_version=2)
        file = SimpleUploadedFile('test.txt', b'hello world', content_type='text/plain')
        response = self.client.post(
            '/api/files/',
            data={'path': '/desktop/test.txt', 'name': 'test.txt', 'file': file},
            HTTP_X_CLIENT_VERSION='1',
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        mock_upload.assert_not_called()

    def test_upload_missing_fields(self):
        response = self.client.post(
            '/api/files/',
            data={'path': '/desktop/test.txt'},
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_missing_file(self):
        response = self.client.post(
            '/api/files/',
            data={'path': '/desktop/test.txt', 'name': 'test.txt'},
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('sync_app.storage.delete_from_minio')
    @patch('sync_app.storage.upload_to_minio')
    def test_upload_prunes_old_versions(self, mock_upload, mock_delete):
        file_obj = File.objects.create(path='/desktop/test.txt', name='test.txt', current_version=5)
        for i in range(1, 6):
            FileVersion.objects.create(
                file=file_obj, version_num=i,
                operation_type='CREATE' if i == 1 else 'MODIFY',
                size=11, storage_path=f'v{i}/desktop/test.txt'
            )

        file = SimpleUploadedFile('test.txt', b'new content', content_type='text/plain')
        response = self.client.post(
            '/api/files/',
            data={'path': '/desktop/test.txt', 'name': 'test.txt', 'file': file},
            HTTP_X_CLIENT_VERSION='5',
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        remaining_versions = FileVersion.objects.filter(file=file_obj).count()
        self.assertEqual(remaining_versions, 5)
        mock_delete.assert_called()


class DeleteFileTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.file = File.objects.create(
            path='/desktop/test.txt',
            name='test.txt',
            current_version=1
        )

    def test_delete_file(self):
        response = self.client.delete(f'/api/files/{self.file.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.file.refresh_from_db()
        self.assertTrue(self.file.is_deleted)

    def test_delete_creates_version(self):
        self.client.delete(f'/api/files/{self.file.id}/')
        version = FileVersion.objects.filter(
            file=self.file,
            operation_type='DELETE'
        ).first()
        self.assertIsNotNone(version)
        self.assertEqual(version.version_num, self.file.current_version)

    @patch('sync_app.storage.move_to_trash')
    def test_delete_moves_files_to_trash(self, mock_move):
        FileVersion.objects.create(
            file=self.file, version_num=1, operation_type='CREATE',
            size=11, storage_path='v1/desktop/test.txt'
        )
        self.client.delete(f'/api/files/{self.file.id}/')
        mock_move.assert_called_once_with('v1/desktop/test.txt', 'trash/v1/desktop/test.txt')

        version = FileVersion.objects.get(file=self.file, operation_type='CREATE')
        self.assertEqual(version.storage_path, 'trash/v1/desktop/test.txt')

    def test_delete_not_found(self):
        fake_id = uuid.uuid4()
        response = self.client.delete(f'/api/files/{fake_id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_already_deleted(self):
        self.file.is_deleted = True
        self.file.save()
        response = self.client.delete(f'/api/files/{self.file.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class RenameFileTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.file = File.objects.create(
            path='/desktop/test.txt',
            name='test.txt',
            current_version=1
        )

    @patch('sync_app.storage.rename_in_minio')
    def test_rename_file(self, mock_rename):
        FileVersion.objects.create(
            file=self.file, version_num=1, operation_type='CREATE',
            size=11, storage_path='v1/desktop/test.txt'
        )
        response = self.client.patch(
            f'/api/files/{self.file.id}/',
            data={'new_name': 'renamed.txt', 'new_path': '/desktop/renamed.txt'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.file.refresh_from_db()
        self.assertEqual(self.file.name, 'renamed.txt')
        self.assertEqual(self.file.path, '/desktop/renamed.txt')

    @patch('sync_app.storage.rename_in_minio')
    def test_rename_updates_storage_path(self, mock_rename):
        FileVersion.objects.create(
            file=self.file, version_num=1, operation_type='CREATE',
            size=11, storage_path='v1/desktop/test.txt'
        )
        self.client.patch(
            f'/api/files/{self.file.id}/',
            data={'new_name': 'renamed.txt', 'new_path': '/desktop/renamed.txt'},
            format='json'
        )
        mock_rename.assert_called_once_with('v1/desktop/test.txt', 'v1/desktop/renamed.txt')

        version = FileVersion.objects.get(file=self.file, operation_type='CREATE')
        self.assertEqual(version.storage_path, 'v1/desktop/renamed.txt')

    @patch('sync_app.storage.rename_in_minio')
    def test_rename_creates_version(self, mock_rename):
        self.client.patch(
            f'/api/files/{self.file.id}/',
            data={'new_name': 'renamed.txt', 'new_path': '/desktop/renamed.txt'},
            format='json'
        )
        version = FileVersion.objects.filter(
            file=self.file,
            operation_type='RENAME'
        ).first()
        self.assertIsNotNone(version)

    def test_rename_not_found(self):
        fake_id = uuid.uuid4()
        response = self.client.patch(
            f'/api/files/{fake_id}/',
            data={'new_name': 'renamed.txt', 'new_path': '/desktop/renamed.txt'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rename_missing_fields(self):
        response = self.client.patch(
            f'/api/files/{self.file.id}/',
            data={},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rename_missing_new_name(self):
        response = self.client.patch(
            f'/api/files/{self.file.id}/',
            data={'new_path': '/desktop/renamed.txt'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rename_deleted_file(self):
        self.file.is_deleted = True
        self.file.save()
        response = self.client.patch(
            f'/api/files/{self.file.id}/',
            data={'new_name': 'renamed.txt', 'new_path': '/desktop/renamed.txt'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DownloadFileTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.file = File.objects.create(
            path='/desktop/test.txt',
            name='test.txt',
            current_version=1
        )
        self.version = FileVersion.objects.create(
            file=self.file,
            version_num=1,
            operation_type='CREATE',
            hash='abc123',
            size=11,
            storage_path='v1/desktop/test.txt'
        )

    @patch('sync_app.storage.download_from_minio')
    def test_download_latest_version(self, mock_download):
        mock_download.return_value = b'hello world'
        response = self.client.get(f'/api/files/{self.file.id}/download/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, b'hello world')
        self.assertIn('attachment', response['Content-Disposition'])
        mock_download.assert_called_once_with('v1/desktop/test.txt')

    @patch('sync_app.storage.download_from_minio')
    def test_download_specific_version(self, mock_download):
        mock_download.return_value = b'hello world'
        response = self.client.get(f'/api/files/{self.file.id}/download/?version=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, b'hello world')

    @patch('sync_app.storage.download_from_minio')
    def test_download_older_version(self, mock_download):
        FileVersion.objects.create(
            file=self.file, version_num=2, operation_type='MODIFY',
            hash='def456', size=15, storage_path='v2/desktop/test.txt'
        )
        self.file.current_version = 2
        self.file.save()

        mock_download.return_value = b'hello world'
        response = self.client.get(f'/api/files/{self.file.id}/download/?version=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_download.assert_called_once_with('v1/desktop/test.txt')

    def test_download_not_found(self):
        fake_id = uuid.uuid4()
        response = self.client.get(f'/api/files/{fake_id}/download/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_download_version_not_found(self):
        response = self.client.get(f'/api/files/{self.file.id}/download/?version=99')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_download_file_with_no_storage_path(self):
        file2 = File.objects.create(path='/desktop/empty.txt', name='empty.txt', current_version=1)
        FileVersion.objects.create(
            file=file2, version_num=1, operation_type='CREATE',
            size=0, storage_path=None
        )
        response = self.client.get(f'/api/files/{file2.id}/download/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class RetrieveFileTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.file = File.objects.create(
            path='/desktop/test.txt',
            name='test.txt',
            current_version=1
        )

    def test_retrieve_file(self):
        response = self.client.get(f'/api/files/{self.file.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['path'], '/desktop/test.txt')
        self.assertEqual(response.data['name'], 'test.txt')
        self.assertEqual(response.data['current_version'], 1)
        self.assertIn('id', response.data)
        self.assertIn('last_modified_time', response.data)

    def test_retrieve_not_found(self):
        fake_id = uuid.uuid4()
        response = self.client.get(f'/api/files/{fake_id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_deleted_file(self):
        self.file.is_deleted = True
        self.file.save()
        response = self.client.get(f'/api/files/{self.file.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class FileHistoryTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.file = File.objects.create(
            path='/desktop/test.txt',
            name='test.txt',
            current_version=2
        )
        FileVersion.objects.create(
            file=self.file, version_num=1, operation_type='CREATE',
            size=11, storage_path='v1/desktop/test.txt'
        )
        FileVersion.objects.create(
            file=self.file, version_num=2, operation_type='MODIFY',
            size=15, storage_path='v2/desktop/test.txt'
        )

    def test_get_history(self):
        response = self.client.get(f'/api/files/{self.file.id}/history/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_history_not_found(self):
        fake_id = uuid.uuid4()
        response = self.client.get(f'/api/files/{fake_id}/history/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_history_ordered_by_version_descending(self):
        response = self.client.get(f'/api/files/{self.file.id}/history/')
        self.assertEqual(response.data[0]['version_num'], 2)
        self.assertEqual(response.data[1]['version_num'], 1)

    def test_history_includes_all_operation_types(self):
        FileVersion.objects.create(
            file=self.file, version_num=2, operation_type='RENAME', size=0
        )
        response = self.client.get(f'/api/files/{self.file.id}/history/')
        operations = [v['operation_type'] for v in response.data]
        self.assertIn('CREATE', operations)
        self.assertIn('MODIFY', operations)
        self.assertIn('RENAME', operations)


class GetChangesTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.file = File.objects.create(
            path='/desktop/test.txt',
            name='test.txt',
            current_version=1
        )
        FileVersion.objects.create(
            file=self.file, version_num=1, operation_type='CREATE',
            size=11, storage_path='v1/desktop/test.txt'
        )

    def test_get_changes_since_beginning(self):
        response = self.client.get('/api/sync/changes?since=1970-01-01T00:00:00Z')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('changes', response.data)
        self.assertIn('last_sync', response.data)
        self.assertEqual(len(response.data['changes']), 1)

    def test_get_changes_since_future(self):
        response = self.client.get('/api/sync/changes?since=2099-01-01T00:00:00Z')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['changes']), 0)

    def test_get_changes_no_since_param(self):
        response = self.client.get('/api/sync/changes')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['changes']), 1)

    def test_get_changes_includes_file_path(self):
        response = self.client.get('/api/sync/changes?since=1970-01-01T00:00:00Z')
        change = response.data['changes'][0]
        self.assertEqual(change['file_path'], '/desktop/test.txt')
        self.assertEqual(change['operation_type'], 'CREATE')

    def test_get_changes_ordered_by_created_at(self):
        file2 = File.objects.create(path='/desktop/file2.txt', name='file2.txt', current_version=1)
        FileVersion.objects.create(
            file=file2, version_num=1, operation_type='CREATE',
            size=5, storage_path='v1/desktop/file2.txt'
        )
        response = self.client.get('/api/sync/changes?since=1970-01-01T00:00:00Z')
        self.assertEqual(len(response.data['changes']), 2)
        self.assertEqual(response.data['changes'][0]['file_path'], '/desktop/test.txt')
        self.assertEqual(response.data['changes'][1]['file_path'], '/desktop/file2.txt')


class GetAllFilesTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        File.objects.create(path='/desktop/file1.txt', name='file1.txt', current_version=1)
        File.objects.create(path='/desktop/file2.txt', name='file2.txt', current_version=1)
        File.objects.create(
            path='/desktop/deleted.txt',
            name='deleted.txt',
            current_version=1,
            is_deleted=True
        )

    def test_get_all_files(self):
        response = self.client.get('/api/files/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_get_all_files_excludes_deleted(self):
        response = self.client.get('/api/files/')
        paths = [f['path'] for f in response.data]
        self.assertNotIn('/desktop/deleted.txt', paths)

    def test_get_all_files_returns_expected_fields(self):
        response = self.client.get('/api/files/')
        file_data = response.data[0]
        self.assertIn('id', file_data)
        self.assertIn('path', file_data)
        self.assertIn('name', file_data)
        self.assertIn('current_version', file_data)
        self.assertIn('last_modified_time', file_data)

    def test_get_all_files_empty(self):
        File.objects.all().delete()
        response = self.client.get('/api/files/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)


class RestoreFileTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.file = File.objects.create(
            path='/desktop/test.txt',
            name='test.txt',
            current_version=1,
            is_deleted=True
        )
        self.version = FileVersion.objects.create(
            file=self.file, version_num=1, operation_type='CREATE',
            size=11, storage_path='trash/v1/desktop/test.txt'
        )

    @patch('sync_app.storage.restore_from_trash')
    def test_restore_file(self, mock_restore):
        response = self.client.post(f'/api/files/{self.file.id}/restore/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.file.refresh_from_db()
        self.assertFalse(self.file.is_deleted)

    @patch('sync_app.storage.restore_from_trash')
    def test_restore_moves_from_trash(self, mock_restore):
        self.client.post(f'/api/files/{self.file.id}/restore/')
        mock_restore.assert_called_once_with('trash/v1/desktop/test.txt', 'v1/desktop/test.txt')

        self.version.refresh_from_db()
        self.assertEqual(self.version.storage_path, 'v1/desktop/test.txt')

    @patch('sync_app.storage.restore_from_trash')
    def test_restore_creates_version(self, mock_restore):
        self.client.post(f'/api/files/{self.file.id}/restore/')
        version = FileVersion.objects.filter(
            file=self.file,
            operation_type='RESTORE'
        ).first()
        self.assertIsNotNone(version)

    def test_restore_not_found(self):
        fake_id = uuid.uuid4()
        response = self.client.post(f'/api/files/{fake_id}/restore/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_restore_non_deleted_file(self):
        self.file.is_deleted = False
        self.file.save()
        response = self.client.post(f'/api/files/{self.file.id}/restore/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
