

try:
    from django.apps import AppConfig
except ImportError:
    # Django < 1.7
    AppConfig = object


class LogAppConfig(AppConfig):
    name = 'djblets.log'
    label = 'djblets_log'
