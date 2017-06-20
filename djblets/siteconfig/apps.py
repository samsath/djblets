

try:
    from django.apps import AppConfig
except ImportError:
    # Django < 1.7
    AppConfig = object


class SiteConfigAppConfig(AppConfig):
    name = 'djblets.siteconfig'
    label = 'djblets_siteconfig'
