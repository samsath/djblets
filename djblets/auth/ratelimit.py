"""Utilities for rate-limiting login attempts."""



import logging
import re
import time

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils import six

from djblets.cache.backend import make_cache_key


logger = logging.getLogger(__name__)


#: The default rate limit for logins.
DEFAULT_LOGIN_LIMIT_RATE = '5/m'


#: The default login rate limit key used for preparing cache keys.
DEFAULT_KEY = 'login-ratelimit'


def get_user_id_or_ip(request):
    """Return the user's ID or IP address from the given HTTP request.

    Args:
        request (django.http.HttpRequest):
            The HTTP request from the client.

    Returns:
        unicode:
        If the user is authenticated, the user ID will be returned.
        Otherwise, the IP address of the client is returned instead.
    """
    if request.user.is_authenticated():
        return six.text_type(request.user.pk)

    try:
        return request.META['HTTP_X_REAL_IP']
    except KeyError:
        try:
            return request.META['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
        except KeyError:
            return request.META['REMOTE_ADDR']


def _get_window(period):
    """Return window period within the given time period.

    This helps determine the time left before the rate limit is over
    for the given user (see 'time_left' variable in get_usage_count()).

    Args:
        period (int):
            The total time period in seconds from the rate.

    Returns:
        int:
        The window period.
    """
    timestamp = int(time.time())

    if period == 1:
        return timestamp

    return timestamp - (timestamp % period) + period


def is_ratelimited(request, increment=False):
    """Check whether the user or IP address has exceeded the rate limit.

    The parameters are used to create a new key or fetch an existing key to
    save or update to the cache and to determine the amount of time period
    left.

    Args:
        request (django.http.HttpRequest):
            The HTTP request from the client.

        increment (bool, optional):
            Whether the number of login attempts should be incremented.

    Returns:
        bool:
        Whether the current user has exceeded the rate limit of login attempts.
    """
    usage = get_usage_count(request, increment)
    return usage['count'] >= usage['limit']


def get_usage_count(request, increment=False):
    """Return rate limit status for a given user or IP address.

    This method performs validation checks on the input parameters
    and creates the cache key to keep track of the
    number of login attempts made by the user. It saves the new
    cache key and initial number of attempts or updates the
    existing cache key and number of attempts before returning
    the count, limit, and time_left.

    Args:
        request (django.http.HttpRequest):
            The HTTP request from the client.

        increment (bool):
            Whether the number of login attempts should be incremented.

    Returns:
        dict:
        A dictionary with the following keys:

        ``count`` (:py:class:`int`):
            The number of login attempts made.

        ``limit`` (:py:class:`int`):
            The number of attempts allowed.

        ``time_left`` (:py:class:`int`):
            The time left before rate limit is over.
    """
    # Obtain specified time limit and period (e.g.: s, m, h, d).
    try:
        limit_str = getattr(settings, 'LOGIN_LIMIT_RATE',
                            DEFAULT_LOGIN_LIMIT_RATE)
        rate_limit = Rate.parse(limit_str)
    except ValueError:
        raise ImproperlyConfigured('LOGIN_LIMIT_RATE setting could not '
                                   'be parsed.')

    limit = rate_limit.count
    period = rate_limit.seconds

    # Determine user ID or IP address from HTTP request.
    user_id_or_ip = get_user_id_or_ip(request)

    # Prepare cache key to add or update to cache and determine remaining time
    # period left.
    cache_key = make_cache_key('%s:%d/%d%s%s' % (DEFAULT_KEY, limit, period,
                                                 user_id_or_ip,
                                                 _get_window(period)))
    time_left = _get_window(period) - int(time.time())

    count = None

    if increment:
        try:
            count = cache.incr(cache_key)
        except ValueError:
            cache.add(cache_key, 1)

    if count is None:
        count = cache.get(cache_key, 0)

    return {
        'count': count,
        'limit': limit,
        'time_left': time_left,
    }


class Rate(object):
    """A rate representing login attempt frequency.

    The main functionality of this class is found in the :py:meth:`parse`
    function. This class converts a rate into a Rate object, which
    contains the number of login attempts allowed within a time period based
    on a given rate string.
    """
    #: Dictionary contains keys that represent different time periods.
    #:
    #: The time periods are represented in seconds for days, hours,
    #: minutes, and seconds.

    PERIODS = {
        's': 1,
        'm': 60,
        'h': 60 * 60,
        'd': 24 * 60 * 60,
    }

    #: Regular expression that interprets the rate string.
    RATE_RE = re.compile(r'(\d+)/(\d*)([smhd])?')

    @classmethod
    def parse(cls, rate_str):
        """Return a Rate parsed from the given rate string.

        Converts the given rate string into a Rate object, which contains
        the number of login attempts allowed (count) and the time period
        alotted for these attempts (seconds).

        Args:
            rate (unicode):
                The number of attempts allowed within a period
                of time (can be seconds, minutes, hours, or days).

        Returns:
            Rate:
            A Rate object that returns the number of login attempts
            allowed (count), and the total time period for these attempts
            (seconds).
        """
        m = Rate.RATE_RE.match(rate_str)

        if m:
            count, multiplier, period = m.groups()
        else:
            raise ValueError('Could not parse given rate: %s.' % rate_str)

        seconds = Rate.PERIODS[period or 's']

        if multiplier:
            seconds *= int(multiplier)

        return cls(count=int(count), seconds=seconds)

    def __init__(self, count, seconds):
        """Initialize attributes for the Rate object.

        This initializes the number of failed login attempts allowed, and
        the time period for the login attempts in seconds based on the
        data returned from the parse() function.

        Args:
            count (int):
                The number of failed login attempts allowed.

            seconds (int):
                The time period for the login attempts in seconds.
        """
        self.count = count
        self.seconds = seconds

    def __eq__(self, other):
        """Return whether the two Rate instances are equal.

        Returns:
            bool:
            Return true if the count and seconds match.
        """
        return (isinstance(other, Rate) and
                self.count == other.count and
                self.seconds == other.seconds)
