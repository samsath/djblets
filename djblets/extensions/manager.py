#
# manager.py -- Extension management and registration.
#
# Copyright (c) 2010-2013  Beanbag, Inc.
# Copyright (c) 2008-2010  Christian Hammond
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



import atexit
import errno
import logging
import os
import pkg_resources
import shutil
import sys
import tempfile
import threading
import time
import traceback
import weakref
from importlib import import_module

from django.conf import settings
from django.conf.urls import include, url
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.urlresolvers import reverse
from django.db import IntegrityError
from django.utils import six
from django.utils.module_loading import module_has_submodule
from django.utils.six.moves import cStringIO as StringIO
from django.utils.translation import ugettext as _
from pipeline.conf import settings as pipeline_settings
from setuptools.command import easy_install

try:
    import django_evolution
except ImportError:
    django_evolution = None

try:
    # Django >= 1.7
    from django.apps.registry import apps
except ImportError:
    # Django == 1.6
    from django.db.models import loading

    apps = None

from djblets.cache.synchronizer import GenerationSynchronizer
from djblets.extensions.errors import (EnablingExtensionError,
                                       InstallExtensionError,
                                       InvalidExtensionError)
from djblets.extensions.extension import ExtensionInfo
from djblets.extensions.models import RegisteredExtension
from djblets.extensions.signals import (extension_initialized,
                                        extension_uninitialized)
from djblets.template.caches import (clear_template_caches,
                                     clear_template_tag_caches)
from djblets.urls.resolvers import DynamicURLResolver
from djblets.util.compat.django.core.files import locks


logger = logging.getLogger(__name__)


class SettingListWrapper(object):
    """Wraps list-based settings to provide management and ref counting.

    This can be used instead of direct access to a list in Django
    settings to ensure items are never added more than once, and only
    removed when nothing needs it anymore.

    Each item in the list is ref-counted. The initial items from the
    setting are populated and start with a ref count of 1. Adding items
    will increment a ref count for the item, adding it to the list
    if it doesn't already exist. Removing items reduces the ref count,
    removing when it hits 0.
    """

    def __init__(self, setting_name, display_name, parent_dict=None):
        """Initialize the settings wrapper.

        Args:
            setting_name (unicode):
                The name of the setting. This is the key in either
                ``parent_dict`` or ``settings``.

            display_name (unicode):
                The display name of the setting, for use in error output.

            parent_dict (dict, optional):
                The dictionary containing the setting. If not set, this
                will fall back to ``settings``.
        """
        self.setting_name = setting_name
        self.display_name = display_name
        self.ref_counts = {}

        parent_dict = parent_dict or settings

        if isinstance(parent_dict, dict):
            self.setting = parent_dict[setting_name]
        else:
            self.setting = getattr(parent_dict, setting_name)

        if isinstance(self.setting, tuple):
            self.setting = list(self.setting)

            if isinstance(parent_dict, dict):
                parent_dict[setting_name] = self.setting
            else:
                setattr(parent_dict, setting_name, self.setting)

        for item in self.setting:
            self.ref_counts[item] = 1

    def add(self, item):
        """Add an item to the setting.

        If the item is already in the list, it won't be added again.
        The ref count will just be incremented.

        If it's a new item, it will be added to the list with a ref count
        of 1.

        Args:
            item (object):
                The item to add.
        """
        if item in self.ref_counts:
            self.ref_counts[item] += 1
        else:
            assert item not in self.setting, \
                ("Extension's %s %s is already in %s in settings, with "
                 "ref count of 0."
                 % (self.display_name, item, self.setting_name))

            self.ref_counts[item] = 1
            self.setting.append(item)

    def add_list(self, items):
        """Add a list of items to the setting.

        Args:
            item (list of object):
                The list of items to add.
        """
        for item in items:
            self.add(item)

    def remove(self, item):
        """Remove an item from the setting.

        The item's ref count will be decremented. If it hits 0, it will
        be removed from the list.

        Args:
            item (object):
                The item to remove.

        Returns:
            bool:
            ``True`` if the item was removed from the list. ``False`` if it
            was left in due to still having a reference.
        """
        assert item in self.ref_counts, \
            ("Extension's %s %s is missing a ref count."
             % (self.display_name, item))
        assert item in self.setting, \
            ("Extension's %s %s is not in %s in settings"
             % (self.display_name, item, self.setting_name))

        if self.ref_counts[item] == 1:
            # This is the very last reference to this item in the list. We
            # can now safely remove it from the list and inform the caller.
            del self.ref_counts[item]
            self.setting.remove(item)

            return True
        else:
            # There's still more references to this item in the list. We can't
            # remove it yet.
            self.ref_counts[item] -= 1

            return False

    def remove_list(self, items):
        """Remove a list of items from the setting.

        Args:
            items (list of object):
                The list of items to remove.

        Returns:
            list of object:
            The list of items that were removed (or that did not exist in
            the list).
        """
        removed_items = []

        for item in items:
            try:
                removed = self.remove(item)
            except ValueError:
                # This may have already been removed. Ignore the error.
                removed = True

            if removed:
                removed_items.append(item)

        return removed_items


class ExtensionManager(object):
    """A manager for all extensions.

    ExtensionManager manages the extensions available to a project. It can
    scan for new extensions, enable or disable them, determine dependencies,
    install into the database, and uninstall.

    An installed extension is one that has been installed by a Python package
    on the system.

    A registered extension is one that has been installed and information then
    placed in the database. This happens automatically after scanning for
    an installed extension. The registration data stores whether or not it's
    enabled, and stores various pieces of information on the extension.

    An enabled extension is one that is actively enabled and hooked into the
    project.

    Each project should have one ExtensionManager.
    """

    #: Whether to explicitly install static media files from packages.
    #:
    #: By default, we install static media files if :django:setting:`DEBUG`
    #: is ``True``. Subclasses can override this to factor in other settings,
    #: if needed.
    should_install_static_media = not settings.DEBUG

    #: The key in the settings indicating the last known configured version.
    #:
    #: This setting is used to differentiate the version of an extension
    #: installed locally on a system and the last version that completed
    #: database-related installation/upgrade steps.
    #:
    #: This should not be changed by subclasses, and generally is not needed
    #: outside of this class.
    VERSION_SETTINGS_KEY = '_extension_installed_version'

    def __init__(self, key):
        self.key = key

        self.pkg_resources = None

        self._extension_classes = {}
        self._extension_instances = {}
        self._load_errors = {}

        # State synchronization
        self._gen_sync = GenerationSynchronizer('extensionmgr:%s:gen' % key)
        self._load_lock = threading.Lock()
        self._shutdown_lock = threading.Lock()
        self._block_sync_gen = False

        self.dynamic_urls = DynamicURLResolver()

        # Extension middleware instances, ordered by dependencies.
        self.middleware = []

        # Wrap the INSTALLED_APPS and TEMPLATE_CONTEXT_PROCESSORS settings
        # to allow for ref-counted add/remove operations.
        self._installed_apps_setting = SettingListWrapper(
            'INSTALLED_APPS',
            'installed app')

        if hasattr(settings, 'TEMPLATES'):
            # Django >= 1.7
            self._context_processors_setting = SettingListWrapper(
                'context_processors',
                'context processor',
                parent_dict=settings.TEMPLATES[0]['OPTIONS'])
        else:
            self._context_processors_setting = SettingListWrapper(
                'TEMPLATE_CONTEXT_PROCESSORS',
                'context processor')

        instance_id = id(self)
        _extension_managers[instance_id] = self

    def get_url_patterns(self):
        """Return the URL patterns for the Extension Manager.

        This should be included in the root urlpatterns for the site.

        Returns:
            list:
            The list of URL patterns for the Extension Manager.
        """
        return [self.dynamic_urls]

    def is_expired(self):
        """Returns whether or not the extension state is possibly expired.

        Extension state covers the lists of extensions and each extension's
        configuration. It can expire if the state synchronization value
        falls out of cache or is changed.

        Each ExtensionManager has its own state synchronization cache key.

        Returns:
            bool:
            Whether the state has expired.
        """
        return self._gen_sync.is_expired()

    def clear_sync_cache(self):
        """Clear the extension synchronization state.

        This will force every process to reload the extension list and
        settings.
        """
        self._gen_sync.clear()

    def get_absolute_url(self):
        return reverse('extension-list')

    def get_can_disable_extension(self, registered_extension):
        extension_id = registered_extension.class_name

        return (registered_extension.extension_class is not None and
                (self.get_enabled_extension(extension_id) is not None or
                 extension_id in self._load_errors))

    def get_can_enable_extension(self, registered_extension):
        return (registered_extension.extension_class is not None and
                self.get_enabled_extension(
                    registered_extension.class_name) is None)

    def get_enabled_extension(self, extension_id):
        """Returns an enabled extension with the given ID."""
        if extension_id in self._extension_instances:
            return self._extension_instances[extension_id]

        return None

    def get_enabled_extensions(self):
        """Returns the list of all enabled extensions."""
        return list(self._extension_instances.values())

    def get_installed_extensions(self):
        """Returns the list of all installed extensions."""
        return list(self._extension_classes.values())

    def get_installed_extension(self, extension_id):
        """Returns the installed extension with the given ID."""
        if extension_id not in self._extension_classes:
            raise InvalidExtensionError(extension_id)

        return self._extension_classes[extension_id]

    def get_dependent_extensions(self, dependency_extension_id):
        """Returns a list of all extensions required by an extension."""
        if dependency_extension_id not in self._extension_instances:
            raise InvalidExtensionError(dependency_extension_id)

        dependency = self.get_installed_extension(dependency_extension_id)
        result = []

        for extension_id, extension in six.iteritems(self._extension_classes):
            if extension_id == dependency_extension_id:
                continue

            for ext_requirement in extension.info.requirements:
                if ext_requirement == dependency:
                    result.append(extension_id)

        return result

    def enable_extension(self, extension_id):
        """Enables an extension.

        Enabling an extension will install any data files the extension
        may need, any tables in the database, perform any necessary
        database migrations, and then will start up the extension.
        """
        if extension_id in self._extension_instances:
            # It's already enabled.
            return

        if extension_id not in self._extension_classes:
            if extension_id in self._load_errors:
                raise EnablingExtensionError(
                    _('There was an error loading this extension'),
                    self._load_errors[extension_id],
                    needs_reload=True)

            raise InvalidExtensionError(extension_id)

        ext_class = self._extension_classes[extension_id]

        # Enable extension dependencies
        for requirement_id in ext_class.requirements:
            self.enable_extension(requirement_id)

        extension = self._init_extension(ext_class)

        ext_class.registration.enabled = True
        ext_class.registration.save()

        clear_template_caches()
        self._bump_sync_gen()
        self._recalculate_middleware()

        return extension

    def disable_extension(self, extension_id):
        """Disables an extension.

        Disabling an extension will remove any data files the extension
        installed and then shut down the extension and all of its hooks.

        It will not delete any data from the database.
        """
        has_load_error = extension_id in self._load_errors

        if not has_load_error:
            if extension_id not in self._extension_instances:
                # It's not enabled.
                return

            if extension_id not in self._extension_classes:
                raise InvalidExtensionError(extension_id)

            extension = self._extension_instances[extension_id]

            for dependent_id in self.get_dependent_extensions(extension_id):
                self.disable_extension(dependent_id)

            self._uninstall_extension(extension)
            self._uninit_extension(extension)
            self._unregister_static_bundles(extension)

            registration = extension.registration
        else:
            del self._load_errors[extension_id]

            if extension_id in self._extension_classes:
                # The class was loadable, so it just couldn't be instantiated.
                # Update the registration on the class.
                ext_class = self._extension_classes[extension_id]
                registration = ext_class.registration
            else:
                registration = RegisteredExtension.objects.get(
                    class_name=extension_id)

        registration.enabled = False
        registration.save(update_fields=['enabled'])

        clear_template_caches()
        self._bump_sync_gen()
        self._recalculate_middleware()

    def install_extension(self, install_url, package_name):
        """Install an extension from a remote source.

        Installs an extension from a remote URL containing the
        extension egg. Installation may fail if a malformed install_url
        or package_name is passed, which will cause an InstallExtensionError
        exception to be raised. It is also assumed that the extension is not
        already installed.
        """

        try:
            easy_install.main(["-U", install_url])

            # Update the entry points.
            dist = pkg_resources.get_distribution(package_name)
            dist.activate()
            pkg_resources.working_set.add(dist)
        except pkg_resources.DistributionNotFound:
            raise InstallExtensionError(_("Invalid package name."))
        except SystemError:
            raise InstallExtensionError(
                _('Installation failed (probably malformed URL).'))

        # Refresh the extension manager.
        self.load(True)

    def load(self, full_reload=False):
        """
        Loads all known extensions, initializing any that are recorded as
        being enabled.

        If this is called a second time, it will refresh the list of
        extensions, adding new ones and removing deleted ones.

        If full_reload is passed, all state is cleared and we reload all
        extensions and state from scratch.
        """
        with self._load_lock:
            self._block_sync_gen = True
            self._load_extensions(full_reload)
            self._block_sync_gen = False

    def shutdown(self):
        """Shut down the extension manager and all of its extensions."""
        with self._shutdown_lock:
            self._clear_extensions()

    def _load_extensions(self, full_reload=False):
        if full_reload:
            # We're reloading everything, so nuke all the cached copies.
            self._clear_extensions()
            clear_template_caches()
            self._load_errors = {}

        # Preload all the RegisteredExtension objects
        registered_extensions = {}
        for registered_ext in RegisteredExtension.objects.all():
            registered_extensions[registered_ext.class_name] = registered_ext

        found_extensions = {}
        found_registrations = {}
        registrations_to_fetch = []
        find_registrations = False
        extensions_changed = False

        for entrypoint in self._entrypoint_iterator():
            registered_ext = None

            try:
                ext_class = entrypoint.load()
            except Exception as e:
                logger.exception('Error loading extension %s: %s',
                                 entrypoint.name, e)
                extension_id = '%s.%s' % (entrypoint.module_name,
                                          '.'.join(entrypoint.attrs))
                self._store_load_error(extension_id, e)
                continue

            # A class's extension ID is its class name. We want to
            # make this easier for users to access by giving it an 'id'
            # variable, which will be accessible both on the class and on
            # instances.
            class_name = ext_class.id = "%s.%s" % (ext_class.__module__,
                                                   ext_class.__name__)
            self._extension_classes[class_name] = ext_class
            found_extensions[class_name] = ext_class

            # Don't override the info if we've previously loaded this
            # class.
            if not getattr(ext_class, 'info', None):
                ext_class.info = ExtensionInfo.create_from_entrypoint(
                    entrypoint, ext_class)

            registered_ext = registered_extensions.get(class_name)

            if registered_ext:
                found_registrations[class_name] = registered_ext

                if not hasattr(ext_class, 'registration'):
                    find_registrations = True
            else:
                registrations_to_fetch.append(
                    (class_name, entrypoint.dist.project_name))
                find_registrations = True

        if find_registrations:
            if registrations_to_fetch:
                stored_registrations = list(
                    RegisteredExtension.objects.filter(
                        class_name__in=registrations_to_fetch))

                # Go through the list of registrations found in the database
                # and mark them as found for later processing.
                for registered_ext in stored_registrations:
                    class_name = registered_ext.class_name
                    found_registrations[class_name] = registered_ext

            # Go through each registration we still need and couldn't find,
            # and create an entry in the database. These are going to be
            # newly discovered extensions.
            for class_name, ext_name in registrations_to_fetch:
                if class_name not in found_registrations:
                    try:
                        registered_ext = RegisteredExtension.objects.create(
                            class_name=class_name,
                            name=ext_name)
                    except IntegrityError:
                        # An entry was created since we last looked up
                        # anything. Fetch it from the database.
                        registered_ext = RegisteredExtension.objects.get(
                            class_name=class_name)

                    found_registrations[class_name] = registered_ext

        # Now we have all the RegisteredExtension instances. Go through
        # and initialize each of them.
        for class_name, registered_ext in six.iteritems(found_registrations):
            ext_class = found_extensions[class_name]
            ext_class.registration = registered_ext

            if (ext_class.registration.enabled and
                ext_class.id not in self._extension_instances):

                try:
                    self._init_extension(ext_class)
                except EnablingExtensionError:
                    # When in debug mode, we want this error to be noticed.
                    # However, in production, it shouldn't break the whole
                    # server, so continue on.
                    if not settings.DEBUG:
                        continue

                extensions_changed = True

        # At this point, if we're reloading, it's possible that the user
        # has removed some extensions. Go through and remove any that we
        # can no longer find.
        #
        # While we're at it, since we're at a point where we've seen all
        # extensions, we can set the ExtensionInfo.requirements for
        # each extension
        for class_name, ext_class in six.iteritems(self._extension_classes):
            if class_name not in found_extensions:
                if class_name in self._extension_instances:
                    self.disable_extension(class_name)

                del self._extension_classes[class_name]
                extensions_changed = True
            else:
                ext_class.info.requirements = \
                    [self.get_installed_extension(requirement_id)
                     for requirement_id in ext_class.requirements]

        # Add the sync generation if it doesn't already exist.
        self._gen_sync.refresh()
        settings.AJAX_SERIAL = self._gen_sync.sync_gen

        if extensions_changed:
            self._recalculate_middleware()

    def _clear_extensions(self):
        """Clear the entire list of known extensions.

        This will bring the ExtensionManager back to the state where
        it doesn't yet know about any extensions, requiring a re-load.
        """
        for extension in self.get_enabled_extensions():
            # Make sure this is actually an enabled extension, and not one
            # that's already been shut down by another instance of this
            # ExtensionManager (which should only happen in tests):
            if hasattr(extension.__class__, 'info'):
                self._uninit_extension(extension)

        for extension_class in self.get_installed_extensions():
            if hasattr(extension_class, 'info'):
                delattr(extension_class, 'info')

            if hasattr(extension_class, 'registration'):
                delattr(extension_class, 'registration')

        self._extension_classes = {}
        self._extension_instances = {}

    def _init_extension(self, ext_class):
        """Initializes an extension.

        This will register the extension, install any URLs that it may need,
        and make it available in Django's list of apps. It will then notify
        that the extension has been initialized.
        """
        extension_id = ext_class.id

        assert extension_id not in self._extension_instances

        try:
            extension = ext_class(extension_manager=self)
        except Exception as e:
            logger.exception('Unable to initialize extension %s: %s',
                             ext_class, e)
            error_details = self._store_load_error(extension_id, e)
            raise EnablingExtensionError(
                _('Error initializing extension: %s') % e,
                error_details)

        if extension_id in self._load_errors:
            del self._load_errors[extension_id]

        self._extension_instances[extension_id] = extension

        if extension.has_admin_site:
            self._init_admin_site(extension)

        # Installing the urls must occur after _init_admin_site(). The urls
        # for the admin site will not be generated until it is called.
        self._install_admin_urls(extension)

        self._register_static_bundles(extension)

        extension.info.installed = extension.registration.installed
        extension.info.enabled = True
        self._add_to_installed_apps(extension)
        self._context_processors_setting.add_list(extension.context_processors)
        clear_template_tag_caches()
        ext_class.instance = extension

        try:
            self.install_extension_media(ext_class)
        except InstallExtensionError as e:
            raise EnablingExtensionError(e.message, e.load_error)

        # Check if the version information stored along with the extension is
        # stale. If so, we may need to perform some updates.
        cur_version = ext_class.info.version

        if ext_class.registration.installed:
            old_version = extension.settings.get(self.VERSION_SETTINGS_KEY)
        else:
            old_version = None

        if (not old_version or
            pkg_resources.parse_version(old_version) <
            pkg_resources.parse_version(cur_version)):
            # We may need to update the database.
            self._sync_database(ext_class)

            # Record this version so we don't update the database again.
            extension.settings.set(self.VERSION_SETTINGS_KEY, cur_version)
            extension.settings.save()
        elif (old_version and
              pkg_resources.parse_version(old_version) >
              pkg_resources.parse_version(cur_version)):
            logging.warning('The version of the "%s" extension installed on '
                            'the server is older than the version recorded '
                            'in the database! Upgrades will not be performed.',
                            ext_class)

        # Mark the extension as installed.
        ext_class.registration.installed = True
        ext_class.registration.save()

        extension_initialized.send(self, ext_class=extension)

        return extension

    def _sync_database(self, ext_class):
        """Synchronize extension-provided models to the database.

        This will create any database tables that need to be created and
        the perform a database migration, if needed.

        Args:
            ext_class (type):
                The extension class owning the database models.
        """
        if apps:
            # Django >= 1.7
            call_command('migrate', run_syncdb=True, verbosity=0,
                         interactive=False)
        else:
            # Django == 1.6
            call_command('syncdb', verbosity=0, interactive=False)

        # Run evolve to do any table modification.
        self._migrate_extension_models(ext_class)

    def _uninit_extension(self, extension):
        """Uninitializes the extension.

        This will shut down the extension, remove any URLs, remove it from
        Django's list of apps, and send a signal saying the extension was
        shut down.
        """
        extension.shutdown()

        if hasattr(extension, "admin_urlpatterns"):
            self.dynamic_urls.remove_patterns(
                extension.admin_urlpatterns)

        if hasattr(extension, "admin_site_urlpatterns"):
            self.dynamic_urls.remove_patterns(
                extension.admin_site_urlpatterns)

        if hasattr(extension, 'admin_site'):
            del extension.admin_site

        self._context_processors_setting.remove_list(
            extension.context_processors)
        self._remove_from_installed_apps(extension)
        clear_template_tag_caches()
        extension.info.enabled = False
        extension_uninitialized.send(self, ext_class=extension)

        del self._extension_instances[extension.id]
        extension.__class__.instance = None

    def _store_load_error(self, extension_id, err):
        """Stores and returns a load error for the extension ID."""
        error_details = '%s\n\n%s' % (err, traceback.format_exc())
        self._load_errors[extension_id] = error_details

        return error_details

    def install_extension_media(self, ext_class, force=False):
        """Installs extension static media.

        This method is a wrapper around _install_extension_media_internal to
        check whether we actually need to install extension media, and avoid
        contention among multiple threads/processes when doing so.

        We need to install extension media if it hasn't been installed yet,
        or if the version of the extension media that we installed is different
        from the current version of the extension.
        """
        # If we're not installing static media, it's assumed that media will
        # be looked up using the static media finders instead. In that case,
        # media will be served directly out of the extension's static/
        # directory. We won't want to be storing version files there.
        if not self.should_install_static_media:
            return

        lockfile = os.path.join(tempfile.gettempdir(), ext_class.id + '.lock')
        media_version_dir = ext_class.info.installed_static_path
        media_version_filename = os.path.join(media_version_dir, '.version')

        cur_version = ext_class.info.version

        # We only want to fetch the existing version information if the
        # extension is already installed. We remove this key when
        # disabling an extension, so if it were there, it was either
        # copy/pasted, or something went wrong. Either way, we wouldn't
        # be able to trust it.
        if force:
            logger.debug('Forcing installation of extension media for %s',
                         ext_class.info)
            old_version = None
        else:
            if (ext_class.registration.installed and
                os.path.exists(media_version_filename)):
                # There's a media version stamp we can read from for this site.
                with open(media_version_filename, 'r') as fp:
                    old_version = fp.read().strip()
            else:
                # This is either a new install, or an older one from before the
                # media version stamp files.
                old_version = None

            if old_version == cur_version:
                # Nothing to do
                return

            if not old_version:
                logger.debug('Installing extension media for %s',
                             ext_class.info)
            else:
                logger.debug('Reinstalling extension media for %s because '
                             'version changed from %s',
                             ext_class.info, old_version)

        while old_version != cur_version:
            with open(lockfile, 'w') as f:
                try:
                    locks.lock(f, locks.LOCK_EX | locks.LOCK_NB)
                except IOError as e:
                    if e.errno in (errno.EAGAIN, errno.EACCES, errno.EINTR):
                        # Sleep for one second, then try again
                        time.sleep(1)

                        # See if the version has changed at all. If so, we'll
                        # be able to break the loop. Otherwise, we're going to
                        # try for the lock again.
                        if os.path.exists(media_version_filename):
                            with open(media_version_filename, 'r') as fp:
                                old_version = fp.read().strip()

                        continue
                    else:
                        raise e

                self._install_extension_media_internal(ext_class)

                try:
                    if not os.path.exists(media_version_dir):
                        os.makedirs(media_version_dir, 0o755)

                    with open(media_version_filename, 'w') as fp:
                        fp.write('%s\n' % cur_version)
                except IOError as e:
                    logging.error('Failed to write static media version file '
                                  '"%s" for extension "%s": %s',
                                  media_version_filename, ext_class.info, e)

                old_version = cur_version

                locks.unlock(f)

        try:
            os.unlink(lockfile)
        except OSError as e:
            # A "No such file or directory" (ENOENT) is most likely due to
            # another thread removing the lock file before this thread could.
            # It's safe to ignore. We want to handle all others, though.
            if e.errno != errno.ENOENT:
                logger.exception("Failed to unlock media lock file '%s' for "
                                 "extension '%s': %s",
                                 lockfile, ext_class.info, e)

    def _install_extension_media_internal(self, ext_class):
        """Install static media for an extension.

        Performs any installation necessary for an extension. If the extension
        has a modern static/ directory, they will be installed into
        :file:`{settings.STATIC_ROOT}/ext/`.
        """
        if pkg_resources.resource_exists(ext_class.__module__, 'htdocs'):
            # This is an older extension that doesn't use the static file
            # support. Log a deprecation notice and then install the files.
            logger.error('The %s extension uses the deprecated "htdocs" '
                         'directory for static files. This is no longer '
                         'supported. It must be updated to use a "static" '
                         'directory instead.',
                         ext_class.info.name)

        ext_static_path = ext_class.info.installed_static_path
        ext_static_path_exists = os.path.exists(ext_static_path)

        if ext_static_path_exists:
            # Also get rid of the old static contents.
            shutil.rmtree(ext_static_path, ignore_errors=True)

            if os.path.exists(ext_static_path):
                logging.critical('Unable to remove old extension media for %s '
                                 'at %s. Make sure this path, its parent, and '
                                 'everything under it is writable by your '
                                 'web server.',
                                 ext_class.info.name, ext_static_path)

        if pkg_resources.resource_exists(ext_class.__module__, 'static'):
            extracted_path = \
                pkg_resources.resource_filename(ext_class.__module__,
                                                'static')

            try:
                shutil.copytree(extracted_path, ext_static_path, symlinks=True)
            except Exception as e:
                logging.critical('Unable to install extension media for %s to '
                                 '%s: %s. The extension may not work, and '
                                 'pages may crash.',
                                 ext_class.info.name, ext_static_path,
                                 exc_info=True)

    def _uninstall_extension(self, extension):
        """Uninstalls extension data.

        Performs any uninstallation necessary for an extension.

        This will uninstall the contents of MEDIA_ROOT/ext/ and
        STATIC_ROOT/ext/.
        """
        extension.settings.set(self.VERSION_SETTINGS_KEY, None)
        extension.settings.save()

        extension.registration.installed = False
        extension.registration.save()

        for path in (extension.info.installed_htdocs_path,
                     extension.info.installed_static_path):
            if os.path.exists(path):
                shutil.rmtree(path, ignore_errors=True)

    def _install_admin_urls(self, extension):
        """Installs administration URLs.

        This provides URLs for configuring an extension, plus any additional
        admin urlpatterns that the extension provides.
        """
        prefix = self.get_absolute_url()

        if hasattr(settings, 'SITE_ROOT'):
            prefix = prefix[len(settings.SITE_ROOT):]

        # Note that we're adding to the resolve list on the root of the
        # install, and prefixing it with the admin extensions path.
        # The reason we're not just making this a child of our extensions
        # urlconf is that everything in there gets passed an
        # extension_manager variable, and we don't want to force extensions
        # to handle this.

        if extension.is_configurable:
            urlconf = extension.admin_urlconf

            if hasattr(urlconf, 'urlpatterns'):
                extension.admin_urlpatterns = [
                    url(r'^%s%s/config/' % (prefix, extension.id),
                        include(urlconf.__name__)),
                ]

                self.dynamic_urls.add_patterns(
                    extension.admin_urlpatterns)

        if getattr(extension, 'admin_site', None):
            extension.admin_site_urlpatterns = [
                url(r'^%s%s/db/' % (prefix, extension.id),
                    include(extension.admin_site.urls)),
            ]

            self.dynamic_urls.add_patterns(
                extension.admin_site_urlpatterns)

    def _register_static_bundles(self, extension):
        """Registers the extension's static bundles with Pipeline.

        Each static bundle will appear as an entry in Pipeline. The
        bundle name and filenames will be changed to include the extension
        ID for the static file lookups.
        """
        def _add_prefix(filename):
            return 'ext/%s/%s' % (extension.id, filename)

        def _add_bundles(pipeline_bundles, extension_bundles, default_dir,
                         ext):
            for name, bundle in six.iteritems(extension_bundles):
                new_bundle = bundle.copy()

                new_bundle['source_filenames'] = [
                    _add_prefix(filename)
                    for filename in bundle.get('source_filenames', [])
                ]

                new_bundle['output_filename'] = _add_prefix(bundle.get(
                    'output_filename',
                    '%s/%s.min%s' % (default_dir, name, ext)))

                pipeline_bundles[extension.get_bundle_id(name)] = new_bundle

        _add_bundles(pipeline_settings.STYLESHEETS, extension.css_bundles,
                     'css', '.css')
        _add_bundles(pipeline_settings.JAVASCRIPT, extension.js_bundles,
                     'js', '.js')

    def _unregister_static_bundles(self, extension):
        """Unregisters the extension's static bundles from Pipeline.

        Every static bundle previously registered will be removed.
        """
        def _remove_bundles(pipeline_bundles, extension_bundles):
            for name, bundle in six.iteritems(extension_bundles):
                try:
                    del pipeline_bundles[extension.get_bundle_id(name)]
                except KeyError:
                    pass

        if hasattr(settings, 'PIPELINE'):
            _remove_bundles(pipeline_settings.STYLESHEETS,
                            extension.css_bundles)

            _remove_bundles(pipeline_settings.JAVASCRIPT,
                            extension.js_bundles)

    def _init_admin_site(self, extension):
        """Creates and initializes an admin site for an extension.

        This creates the admin site and imports the extensions admin
        module to register the models.

        The url patterns for the admin site are generated in
        _install_admin_urls().
        """
        extension.admin_site = AdminSite(extension.info.app_name)

        # Import the extension's admin module.
        try:
            admin_module_name = '%s.admin' % extension.info.app_name
            if admin_module_name in sys.modules:
                # If the extension has been loaded previously and
                # we are re-enabling it, we must reload the module.
                # Just importing again will not cause the ModelAdmins
                # to be registered.
                reload(sys.modules[admin_module_name])
            else:
                import_module(admin_module_name)
        except ImportError:
            mod = import_module(extension.info.app_name)

            # Decide whether to bubble up this error. If the app just
            # doesn't have an admin module, we can ignore the error
            # attempting to import it, otherwise we want it to bubble up.
            if module_has_submodule(mod, 'admin'):
                raise ImportError(
                    "Importing admin module for extension %s failed"
                    % extension.info.app_name)

    def _add_to_installed_apps(self, extension):
        """Add an extension's apps to the list of installed apps.

        This will register each app with Django and clear any caches needed
        to load the extension's modules.

        Args:
            extension (djblets.extensions.extension.Extension):
                The extension whose apps are being added.
        """
        self._installed_apps_setting.add_list(
            extension.apps or [extension.info.app_name])

        if apps:
            # Django >= 1.7
            apps.set_installed_apps(settings.INSTALLED_APPS)
        else:
            # Django == 1.6
            loading.cache.loaded = False

    def _remove_from_installed_apps(self, extension):
        """Remove an extension's apps from the list of installed apps.

        This will unregister each app with Django and clear any caches
        storing the apps' models.

        Args:
            extension (djblets.extensions.extension.Extension):
                The extension whose apps are being removed.
        """
        # Remove the extension's apps from INSTALLED_APPS.
        removed_apps = self._installed_apps_setting.remove_list(
            extension.apps or [extension.info.app_name])

        # Now clear the apps and their modules from any caches.
        if apps:
            apps.unset_installed_apps()
        else:
            for app_name in removed_apps:
                # In Django 1.6, the only apps that are registered are those
                # with models. If this particular app does not have models, we
                # don't want to clear any caches below. There might be another
                # app with the same label that actually does have models, and
                # we'd be clearing those away. An example would be
                # reviewboard.hostingsvcs (which has models) and
                # rbpowerpack.hostingsvcs (which does not).
                #
                # Django 1.6 doesn't technically allow multiple apps with the
                # same label to have models (other craziness will happen), so
                # we don't have to worry about that. It's not our problem.
                try:
                    app_mod = import_module('%s.models' % app_name)
                except ImportError:
                    # Something went very wrong. Maybe this module didn't
                    # exist anymore. Ignore it.
                    continue

                # Fetch the models before we make any changes to the cache.
                model_modules = {app_mod}
                model_modules.update(
                    import_module(model.__module__)
                    for model in loading.get_models(app_mod)
                )

                # Start pruning this app from the caches.
                #
                # We are going to keep this in loading.cache.app_models.
                # If we don't, we'll never get those modules again without
                # some potentially dangerous manipulation of sys.modules and
                # possibly other state. get_models() will default to ignoring
                # anything in that list if the app label isn't present in
                # loading.cache.app_labels, which we'll remove, so the model
                # will appear as "uninstalled."
                app_label = app_name.rpartition('.')[2]
                loading.cache.app_labels.pop(app_label, None)

                for module in model_modules:
                    loading.cache.app_store.pop(module, None)

            # Force get_models() to recompute models for lookups, so that
            # now-unregistered models aren't returned.
            loading.cache._get_models_cache.clear()
            loading.cache.loaded = False

    def _entrypoint_iterator(self):
        return pkg_resources.iter_entry_points(self.key)

    def _bump_sync_gen(self):
        """Bumps the synchronization generation value.

        If there's an existing synchronization generation in cache,
        increment it. Otherwise, start fresh with a new one.

        This will also set ``settings.AJAX_SERIAL``, which will guarantee any
        cached objects that depends on templates and use this serial number
        will be invalidated, allowing TemplateHooks and other hooks
        to be re-run.
        """
        # If we're in the middle of loading extension state, perhaps due to
        # the sync number being bumped by another process, this flag will be
        # sent in order to block any further attempts at bumping the number.
        # Failure to do this can result in a loop where the number gets
        # bumped by every process/thread reacting to another process/thread
        # bumping the number, resulting in massive slowdown and errors.
        if self._block_sync_gen:
            return

        self._gen_sync.mark_updated()
        settings.AJAX_SERIAL = self._gen_sync.sync_gen

    def _migrate_extension_models(self, ext_class):
        """Perform database migrations for an extension's models.

        This will call out to Django Evolution to handle the migrations.

        Args:
            ext_class (djblets.extensions.extension.Extension):
                The class for the extension to migrate.
        """
        if django_evolution is None:
            # Django Evolution isn't installed. Extensions with evolutions
            # are not supported.
            return

        try:
            stream = StringIO()
            call_command('evolve',
                         verbosity=0,
                         interactive=False,
                         execute=True,
                         stdout=stream,
                         stderr=stream)
            output = stream.getvalue()

            if output:
                logger.info('Evolved extension models for %s: %s',
                            ext_class.id, stream.read())

            stream.close()
        except CommandError as e:
            # Something went wrong while running django-evolution, so
            # grab the output.  We can't raise right away because we
            # still need to put stdout back the way it was
            output = stream.getvalue()
            stream.close()

            logger.exception('Error evolving extension models: %s: %s',
                             e, output)

            load_error = self._store_load_error(ext_class.id, output)
            raise InstallExtensionError(six.text_type(e), load_error)

    def _recalculate_middleware(self):
        """Recalculates the list of middleware."""
        self.middleware = []
        done = set()

        for e in self.get_enabled_extensions():
            self.middleware.extend(self._get_extension_middleware(e, done))

    def _get_extension_middleware(self, extension, done):
        """Returns a list of middleware for 'extension' and its dependencies.

        This is a recursive utility function initially called by
        _recalculate_middleware() that ensures that middleware for all
        dependencies are inserted before that of the given extension.  It
        also ensures that each extension's middleware is inserted only once.
        """
        middleware = []

        if extension in done:
            return middleware

        done.add(extension)

        for req in extension.requirements:
            e = self.get_enabled_extension(req)

            if e:
                middleware.extend(self._get_extension_middleware(e, done))

        middleware.extend(extension.middleware_instances)
        return middleware


_extension_managers = weakref.WeakValueDictionary()


def get_extension_managers():
    """Return all extension manager instances.

    This will return all the extension managers that have been constructed.
    The order is not guaranteed.

    Returns:
        list: The list of ExtensionManager instances.
    """
    return list(_extension_managers.values())


def shutdown_extension_managers():
    """Shut down all extension managers.

    This is called automatically when the process exits, but can be run
    manually.
    """
    for extension_manager in get_extension_managers():
        extension_manager.shutdown()


# When the process ends, shut down the extensions on this manager.
# That will help work around bugs in Django where it attempts to
# work with garbage state being held onto by extensions.
atexit.register(shutdown_extension_managers)
