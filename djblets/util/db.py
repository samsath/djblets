
import warnings

from djblets.db.managers import ConcurrencyManager


warnings.warn('djblets.util.db is deprecated', DeprecationWarning)


__all__ = ['ConcurrencyManager']
