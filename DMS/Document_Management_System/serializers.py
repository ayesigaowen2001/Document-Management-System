# =============================================================================
# DMS/Document_Management_System/serializers.py — Serializers
# =============================================================================
# This module defines all DRF serializers for the Document Management System.
#
# Serializers are categorised as follows:
#
# Model serializers (directly mirror database models):
#   - AuthUserSerializer         → auth.User (built-in Django auth user)
#   - AdminProfileSerializer      → AdminProfile
#   - UserProfileSerializer       → UserProfile
#   - UserGroupSerializer         → UserGroup
#   - DocumentSerializer          → Document
#   - DocumentShareSerializer     → DocumentShare  (with custom validation)
#
# Non-model serializers (used for request validation / ad-hoc data):
#   - UserGroupAddMemberSerializer              – validate adding a member to a group
#   - DocumentPermissionAssignmentSerializer    – validate permission assignment payload
#   - UserUpdateSerializer                      – validate partial user updates
#   - AccountCreateSerializer                   – validate new account creation
# =============================================================================

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import AdminProfile, Document, DocumentShare, UserGroup, UserProfile


User = get_user_model()

# The complete set of document-level permission codenames recognised by the
# system.  These are used as choices in DocumentPermissionAssignmentSerializer.
DOCUMENT_PERMISSION_CHOICES = [
    'view_document',
    'add_document',
    'change_document',
    'delete_document',
    'share_document',
]


# ---------------------------------------------------------------------------
# Model serializers
# ---------------------------------------------------------------------------

class AuthUserSerializer(serializers.ModelSerializer):
    """
    Serializer for Django's built-in auth.User model (auth_users table).

    Handles password hashing on create/update. The password field is
    write-only and excluded from all responses.
    """
    password = serializers.CharField(write_only=True, min_length=8, required=False)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'password',
            'first_name',
            'last_name',
            'is_staff',
            'is_superuser',
            'is_active',
            'date_joined',
            'last_login',
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']
        extra_kwargs = {
            'password': {'write_only': True},
        }

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AdminProfileSerializer(serializers.ModelSerializer):
    """Serializer for the AdminProfile model (admin users)."""
    class Meta:
        model = AdminProfile
        fields = ['id', 'user', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for the UserProfile model (regular users)."""
    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'created_by', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserGroupSerializer(serializers.ModelSerializer):
    """Serializer for the UserGroup model (groups of regular users)."""
    class Meta:
        model = UserGroup
        fields = ['id', 'name', 'description', 'created_by', 'members', 'created_at']
        read_only_fields = ['id', 'created_at']


class DocumentSerializer(serializers.ModelSerializer):
    """Serializer for the Document model (uploaded files)."""
    class Meta:
        model = Document
        fields = ['id', 'title', 'file', 'uploaded_by', 'group', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at', 'uploaded_by']


class DocumentShareSerializer(serializers.ModelSerializer):
    """
    Serializer for the DocumentShare model.

    **Input** (write-only):
      - ``email``       – Email address of the UserProfile to share with.
      - ``group_name``  – Name of the UserGroup to share with.

    Exactly one of ``email`` or ``group_name`` must be supplied.  The
    serializer resolves the given identifier to the corresponding model
    instance internally, so callers never need to know database primary keys.

    **Output** (read-only):
      Returns the standard DocumentShare representation including the
      ``shared_with_user`` (pk) and ``shared_with_group`` (pk) fields.
    """
    email = serializers.EmailField(write_only=True, required=False)
    group_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = DocumentShare
        fields = [
            'id',
            'document',
            'shared_by',
            'shared_with_user',
            'shared_with_group',
            'email',
            'group_name',
            'created_at',
        ]
        read_only_fields = ['id', 'document', 'shared_by', 'shared_with_user', 'shared_with_group', 'created_at']

    def validate(self, attrs):
        """
        Ensure exactly one of ``email`` or ``group_name`` is provided,
        then resolve it to the appropriate model instance.

        On success, the validated data will contain either a
        ``shared_with_user`` (UserProfile) or ``shared_with_group`` (UserGroup)
        key so that callers can directly use it with ``get_or_create``.
        """
        email = attrs.pop('email', None)
        group_name = attrs.pop('group_name', None)

        if bool(email) == bool(group_name):
            raise serializers.ValidationError('Provide either email or group_name (not both, not neither).')

        if email:
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                raise serializers.ValidationError(f"No user found with email '{email}'.")

            user_profile = getattr(user, 'user_profile', None)
            if user_profile is None:
                raise serializers.ValidationError(f"User with email '{email}' does not have a user profile.")
            attrs['shared_with_user'] = user_profile
        else:
            try:
                group = UserGroup.objects.get(name=group_name)
            except UserGroup.DoesNotExist:
                raise serializers.ValidationError(f"No group found with name '{group_name}'.")
            attrs['shared_with_group'] = group

        return attrs


# ---------------------------------------------------------------------------
# Non-model (input-validation) serializers
# ---------------------------------------------------------------------------

class UserGroupAddMemberSerializer(serializers.Serializer):
    """
    Validates the payload for adding a user to a group.
    Accepts an `email` address of the user to add (looked up via the auth User model).
    """
    email = serializers.EmailField()

    def validate_email(self, value):
        """
        Look up the User by email, then find their UserProfile.
        Raise a validation error if not found.
        """
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(f"No user found with email '{value}'.")

        user_profile = getattr(user, 'user_profile', None)
        if user_profile is None:
            raise serializers.ValidationError(f"User with email '{value}' does not have a user profile.")

        return user_profile


class DocumentPermissionAssignmentSerializer(serializers.Serializer):
    """
    Validates the payload for assigning document permissions to a user.
    Accepts:
      - email        : email of the target User
      - permissions  : non-empty list of permission codenames
    """
    email = serializers.EmailField()
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=DOCUMENT_PERMISSION_CHOICES),
        allow_empty=False,
    )

    def validate_email(self, value):
        """
        Look up the User by email. Raise a validation error if not found
        or if the user is staff/superuser.
        """
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(f"No user found with email '{value}'.")

        if user.is_staff or user.is_superuser:
            raise serializers.ValidationError('Permissions can only be assigned to regular users.')

        return user


class UserUpdateSerializer(serializers.Serializer):
    """
    Validates partial user-update payloads (used by PATCH endpoints).
    All fields are optional; only supplied fields are applied.
    """
    username = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True, min_length=8, required=False)


class AccountCreateSerializer(serializers.Serializer):
    """
    Validates the payload for creating a new account (admin or user).
    All fields are required.
    """
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
