

try:
    from django.apps import AppConfig
except ImportError:
    # Django < 1.7
    AppConfig = object


class FormsAppConfig(AppConfig):
    name = 'djblets.forms'
    label = 'djblets_forms'
