"""A base form for working with settings stored on SiteConfigurations."""



from djblets.forms.forms import KeyValueForm


class SiteSettingsForm(KeyValueForm):
    """A base form for loading/saving settings for a SiteConfiguration.

    This is meant to be subclassed for different settings pages. Any fields
    defined by the form will be loaded/saved automatically.
    """

    def __init__(self, siteconfig, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.siteconfig = siteconfig

        super(SiteSettingsForm, self).__init__(instance=siteconfig,
                                               *args, **kwargs)

    def get_key_value(self, key, default=None):
        """Return the value for a SiteConfiguration settings key.

        Args:
            key (unicode):
                The settings key.

            default (object):
                The default value from the form, which will be ignored,
                so that the registered siteconfig defaults will be used.

        Returns:
            object:
            The resulting value from the settings.
        """
        return self.instance.get(key)

    def set_key_value(self, key, value):
        """Set the value for a SiteConfiguration settings key.

        Args:
            key (unicode):
                The settings key.

            value (object):
                The settings value.
        """
        self.instance.set(key, value)

    def save_instance(self):
        """Save the SiteConfiguration instance."""
        self.instance.save()
