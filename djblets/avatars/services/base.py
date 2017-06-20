"""The base avatar service class implementation."""



from django.template.loader import render_to_string


class AvatarService(object):
    """A service that provides avatar support.

    At the very least, subclasses must set the :py:attr:`avatar_service_id` and
    :py:attr:`name` attributes, as well as override the
    :py:meth:`get_avatar_urls` method.
    """

    #: The avatar service's ID.
    #:
    #: This must be unique for every avatar service subclass.
    avatar_service_id = None

    #: The avatar service's human-readable name.
    name = None

    #: The template for rendering the avatar as HTML.
    template_name = 'avatars/avatar.html'

    #: An optional form to provide per-user configuration for the service.
    #:
    #: This should be a sub-class of
    # :py:class:`djblets.avatars.forms.AvatarServiceConfigForm`.
    config_form_class = None

    #: Whether or not the avatar service is hidden from users.
    #:
    #: Hidden avatar services are not exposed to users and are intended to be
    #: used only internally, such as with extensions providing bots.
    hidden = False

    def __init__(self, settings_manager_class):
        """Initialize the avatar service.

        Args:
            settings_manager_class (type):
                The :py:class:`AvatarSettingsManager` subclass to use for
                managing settings.
        """
        self._settings_manager_class = settings_manager_class

    @classmethod
    def is_configurable(cls):
        """Return whether or not the service is configurable.

        Returns:
            bool:
            Whether or not the service is configurable.
        """
        return cls.config_form_class is not None

    def get_configuration_form(self, user, *args, **kwargs):
        """Return an instantiated configuration form.

        Args:
            user (django.contrib.auth.models.User):
                The user.

            *args (tuple):
                Additional positional arguments to pass to the configuration
                form constructor.

            **kwargs (dict):
                Additional keyword arguments to pass to the configuration form
                constructor.

        Returns:
            djblets.avatars.forms.AvatarServiceConfigForm:
            The form, instantiated with the user's configuration, or ``None``
            if the service is not configurable (i.e., does not have a
            configuration form).
        """
        if not self.is_configurable():
            return None

        configuration = (
            self._settings_manager_class(user)
                .configuration_for(self.avatar_service_id)
        )

        return self.config_form_class(configuration=configuration,
                                      service=self,
                                      prefix=self.avatar_service_id,
                                      *args,
                                      **kwargs)

    def get_avatar_urls(self, request, user, size):
        """Render the avatar URLs for the given user.

        The result of calls to this method will be cached on the request for
        the specified user, service, and size.

        Args:
            request (django.http.HttpRequest):
                The HTTP request.

            user (django.contrib.auth.models.User):
                The user for whom the avatar URLs are to be retrieved.

            size (int):
                The requested avatar size (height and width) in pixels.

        Returns:
            dict:
                A dictionary mapping resolutions to URLs as
                :py:class:`django.utils.safestring.SafeText` objects
                The dictionary must support at least the following resolutions:

                ``'1x'``:
                    The user's regular avatar.

                ``'2x'``:
                    The user's avatar at twice the resolution.

                ``'3x'``:
                    The user's avatar at three times the resolution.

                Any key except for ``'1x'`` may be ``None``.

                The URLs **must** be safe, or rendering errors will occur.
                Explicitly sanitize them and use
                :py:math:`django.utils.html.mark_safe`.
        """
        if not hasattr(request, '_avatar_cache'):
            request._avatar_cache = {}

        key = (user.pk, self.avatar_service_id, size)

        try:
            urls = request._avatar_cache[key]
        except KeyError:
            urls = self.get_avatar_urls_uncached(user, size)
            request._avatar_cache[key] = urls

        return urls

    def get_avatar_urls_uncached(self, user, size):
        """Return the avatar URLs for the given user.

        Subclasses must override this to provide the actual URLs.

        Args:
            user (django.contrib.auth.models.User):
                The user for whom the avatar URLs are to be retrieved.

            size (int, optional):
                The requested avatar size (height and width) in pixels.

        Returns:
            dict:
                A dictionary of the URLs for the requested user. The
                dictionary will have the following keys:

                * ``'1x'``: The user's regular avatar.
                * ``'2x'``: The user's avatar at twice the resolution
                  (e.g., for retina displays). This may be ``None``.
                * ``'3x'``: The user's avatar at three times the resolution.
                  This may be ``None``.

                The URLs returned by this function **must** be safe, i.e., they
                should be able to be injected into HTML without being
                sanitized. They should be marked safe explicitly via
                :py:meth:`django.utils.html.mark_safe`.
        """
        raise NotImplementedError(
            '%r must implement get_avatar_urls_uncached().'
            % type(self)
        )

    def render(self, request, user, size):
        """Render a user's avatar to HTML.

        By default, this is rendered with the template specified by the
        :py:attr:`template_name` attribute. This behaviour can be overridden
        by subclasses.

        Args:
            request (django.http.HttpRequest):
                The HTTP request.

            user (django.contrib.auth.models.User):
                The user for whom the avatar is to be rendered.

            size (int):
                The requested avatar size (height and width) in pixels.

        Returns:
            unicode: The rendered avatar HTML.
        """
        return render_to_string(self.template_name, {
            'urls': self.get_avatar_urls(request, user, size),
            'username': user.get_full_name() or user.username,
            'size': size,
        })

    def cleanup(self, user):
        """Clean up state when a user no longer uses this service.

        Subclasses may use this to clean up database state or remove files. By
        default, this method does nothing.

        Args:
            user (django.contrib.auth.models.User):
                The user who is no longer using the service.
        """
        pass

    def get_etag_data(self, user):
        """Return ETag data for the user's avatar.

        ETags (Entity Tags) are used in caching HTTP request results. The data
        returned by this function should be a list of
        :py:class:`unicode strings <unicode>` that uniquely represent the
        avatar service and its configuration.

        Subclasses must implement this method.

        Args:
            user (django.contrib.auth.models.User):
                The user.

        Returns:
            list of unicode:
            The uniquely identifying information for the user's avatar.
        """
        raise NotImplementedError(
            '%s must implement get_etag_data' % type(self).__name__
        )
