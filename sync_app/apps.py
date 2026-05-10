from django.apps import AppConfig

class SyncAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sync_app'

    def ready(self):
        from . import storage
        storage.set_trash_lifecycle_policy()
