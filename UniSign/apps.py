from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class UniSignConfig(AppConfig):
    name = 'UniSign'
    verbose_name = _("سامانه حضور و غیاب")

    def ready(self):
        import UniSign.signals