"""Djblets Avatar Services."""



from djblets.avatars.services.base import AvatarService
from djblets.avatars.services.file_upload import FileUploadService
from djblets.avatars.services.gravatar import GravatarService
from djblets.avatars.services.url import URLAvatarService


__all__ = (
    'AvatarService',
    'FileUploadService',
    'GravatarService',
    'URLAvatarService',
)
