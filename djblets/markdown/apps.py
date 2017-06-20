

try:
    from django.apps import AppConfig
except ImportError:
    # Django < 1.7
    AppConfig = object


class MarkdownAppConfig(AppConfig):
    name = 'djblets.markdown'
    label = 'djblets_markdown'
