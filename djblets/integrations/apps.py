

try:
    from django.apps import AppConfig
except ImportError:
    # Django < 1.7
    AppConfig = object


class IntegrationsAppConfig(AppConfig):
    name = 'djblets.integrations'
    label = 'djblets_integrations'
