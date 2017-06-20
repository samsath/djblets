

try:
    from django.apps import AppConfig
except ImportError:
    # Django < 1.7
    AppConfig = object


class ConfigFormsAppConfig(AppConfig):
    name = 'djblets.configforms'
    label = 'djblets_configforms'
