

try:
    from django.apps import AppConfig
except ImportError:
    # Django < 1.7
    AppConfig = object


class ExtensionsAppConfig(AppConfig):
    name = 'djblets.extensions'
    label = 'djblets_extensions'
