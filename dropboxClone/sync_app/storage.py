import boto3
from botocore.client import Config
from django.conf import settings

s3 = boto3.client(
    's3',
    endpoint_url=settings.MINIO_ENDPOINT,
    aws_access_key_id=settings.MINIO_ACCESS_KEY,
    aws_secret_access_key=settings.MINIO_SECRET_KEY,
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)

def upload_to_storage(file_data, storage_key):
    s3.put_object(
        Bucket=settings.MINIO_BUCKET,
        Key=storage_key,
        Body=file_data
    )

def download_from_storage(storage_key):
    response = s3.get_object(
        Bucket=settings.MINIO_BUCKET,
        Key=storage_key
    )
    return response['Body'].read()

def delete_from_storage(storage_key):
    s3.delete_object(
        Bucket=settings.MINIO_BUCKET,
        Key=storage_key
    )

def move_to_trash(source_key, trash_key):
    s3.copy_object(
        Bucket=settings.MINIO_BUCKET,
        CopySource={'Bucket': settings.MINIO_BUCKET, 'Key': source_key},
        Key=trash_key
    )
    s3.delete_object(
        Bucket=settings.MINIO_BUCKET,
        Key=source_key
    )

def restore_from_trash(trash_key, original_key):
    s3.copy_object(
        Bucket=settings.MINIO_BUCKET,
        CopySource={'Bucket': settings.MINIO_BUCKET, 'Key': trash_key},
        Key=original_key
    )
    s3.delete_object(
        Bucket=settings.MINIO_BUCKET,
        Key=trash_key
    )

def set_trash_lifecycle_policy():
    lifecycle_config = {
        'Rules': [
            {
                'ID': 'trash-expiry',
                'Status': 'Enabled',
                'Filter': {'Prefix': 'trash/'},
                'Expiration': {'Days': settings.TRASH_EXPIRY_DAYS}
            }
        ]
    }
    s3.put_bucket_lifecycle_configuration(
        Bucket=settings.MINIO_BUCKET,
        LifecycleConfiguration=lifecycle_config
    )


def rename_in_storage(old_key, new_key):
    s3.copy_object(
        Bucket=settings.MINIO_BUCKET,
        CopySource={'Bucket': settings.MINIO_BUCKET, 'Key': old_key},
        Key=new_key
    )
    s3.delete_object(
        Bucket=settings.MINIO_BUCKET,
        Key=old_key
    )