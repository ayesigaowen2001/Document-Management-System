# =============================================================================
# DMS/Document_Management_System/authentication.py – Custom Auth Backend
# =============================================================================
# This module defines a custom DRF authentication class that validates
# requests using SessionToken (defined in models.py).
#
# Unlike DRF's built-in Token model (OneToOneField → only one token per user),
# SessionToken uses a ForeignKey so a user can have multiple simultaneous sessions.
#
# After login, clients pass the token in the header:
#   Authorization: Token <session_token_key>
# =============================================================================

from rest_framework import authentication, exceptions

from .models import SessionToken


class SessionTokenAuthentication(authentication.TokenAuthentication):
    """
    Custom DRF authentication backend that validates requests using
    ``SessionToken`` instead of the built-in ``Token`` model.

    Usage
    -----
    Clients must include the token in the ``Authorization`` HTTP header::

        Authorization: Token 0123456789abcdef0123456789abcdef01234567

    The model field name mirrors DRF's ``Token.key`` so that the parent
    class's ``authenticate_credentials`` works without modification.
    """
    model = SessionToken

    def authenticate_credentials(self, key):  # type: ignore[override]
        """
        Override to check token expiry after the parent authenticates.
        """

        try:
            token = self.model.objects.select_related('user').get(key=key)
        except self.model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token.')

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted.')

        if token.is_expired:
            token.delete()
            raise exceptions.AuthenticationFailed('Token has expired.')

        return (token.user, token)
