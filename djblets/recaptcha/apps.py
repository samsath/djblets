

try:
    from django.apps import AppConfig
except ImportError:
    # Django < 1.7
    AppConfig = object


class RecaptchaAppConfig(AppConfig):
    name = 'djblets.recaptcha'
    label = 'djblets_recaptcha'
