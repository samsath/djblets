#
# models.py -- Models for the siteconfig app
#
# Copyright (c) 2008-2009  Christian Hammond
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#



from django.contrib.sites.models import Site
from django.db import models
from django.utils import six
from django.utils.encoding import python_2_unicode_compatible

from djblets.cache.synchronizer import GenerationSynchronizer
from djblets.db.fields import JSONField
from djblets.siteconfig.managers import SiteConfigurationManager


_DEFAULTS = {}


class SiteConfigSettingsWrapper(object):
    """Wraps the settings for a SiteConfiguration.

    This is used by the context processor for templates to wrap accessing
    settings data, properly returning defaults.
    """
    def __init__(self, siteconfig):
        self.siteconfig = siteconfig

    def __getattr__(self, key):
        return self.siteconfig.get(key)


@python_2_unicode_compatible
class SiteConfiguration(models.Model):
    """
    Configuration data for a site. The version and all persistent settings
    are stored here.

    The usual way to retrieve a SiteConfiguration is to use
    :py:meth:`get_current`.
    """

    site = models.ForeignKey(Site, related_name="config")
    version = models.CharField(max_length=20)

    #: A JSON dictionary field of settings stored for a site.
    settings = JSONField()

    objects = SiteConfigurationManager()

    def __init__(self, *args, **kwargs):
        models.Model.__init__(self, *args, **kwargs)

        # Optimistically try to set the Site to the current site instance,
        # which either is cached now or soon will be. That way, we avoid
        # a lookup on the relation later.
        cur_site = Site.objects.get_current()

        if cur_site.pk == self.site_id:
            self.site = cur_site

        # Begin managing the synchronization of settings between all
        # SiteConfigurations.
        self._gen_sync = GenerationSynchronizer(
            '%s:siteconfig:%s:generation' % (self.site.domain, self.pk))

        self.settings_wrapper = SiteConfigSettingsWrapper(self)

    def get(self, key, default=None):
        """
        Retrieves a setting. If the setting is not found, the default value
        will be returned. This is represented by the default parameter, if
        passed in, or a global default if set.
        """
        if default is None and self.id in _DEFAULTS:
            default = _DEFAULTS[self.id].get(key, None)

        return self.settings.get(key, default)

    def set(self, key, value):
        """
        Sets a setting. The key should be a string, but the value can be
        any native Python object.
        """
        self.settings[key] = value

    def add_defaults(self, defaults_dict):
        """Add a dictionary of defaults.

        These defaults will be used when calling :py:meth:`get`, if that
        setting wasn't saved in the database.
        """
        if self.id not in _DEFAULTS:
            _DEFAULTS[self.id] = {}

        _DEFAULTS[self.id].update(defaults_dict)

    def add_default(self, key, default_value):
        """
        Adds a single default setting.
        """
        self.add_defaults({key: default_value})

    def get_defaults(self):
        """
        Returns all default settings registered with this SiteConfiguration.
        """
        if self.id not in _DEFAULTS:
            _DEFAULTS[self.id] = {}

        return _DEFAULTS[self.id]

    def is_expired(self):
        """Return whether or not this SiteConfiguration is expired.

        If the configuration is expired, it will need to be reloaded before
        accessing any settings.

        Returns:
            bool:
            Whether or not the current state is expired.
        """
        return self._gen_sync.is_expired()

    def save(self, clear_caches=True, **kwargs):
        self._gen_sync.mark_updated()

        if clear_caches:
            # The cached siteconfig might be stale now. We'll want a refresh.
            # Also refresh the Site cache, since callers may get this from
            # Site.config.
            SiteConfiguration.objects.clear_cache()
            Site.objects.clear_cache()

        super(SiteConfiguration, self).save(**kwargs)

    def __str__(self):
        return "%s (version %s)" % (six.text_type(self.site), self.version)

    class Meta:
        # Djblets 0.9+ sets an app label of "djblets_siteconfig" on
        # Django 1.7+, which would affect the table name. We need to retain
        # the old name for backwards-compatibility.
        db_table = 'siteconfig_siteconfiguration'
