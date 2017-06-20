

try:
    from django.apps import AppConfig
except ImportError:
    # Django < 1.7
    AppConfig = object


class AuthAppConfig(AppConfig):
    name = 'djblets.auth'
    label = 'djblets_auth'
