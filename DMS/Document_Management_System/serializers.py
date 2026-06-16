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


class UserBriefSerializer(serializers.ModelSerializer):
    """
    Compact serializer for the built-in User model.
    Returns a subset of fields (id, username, email).
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class AdminProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the AdminProfile model (admin users).

    The ``user`` field is a nested representation containing
    ``id``, ``username``, and ``email`` of the related auth.User.
    """
    user = UserBriefSerializer(read_only=True)

    class Meta:
        model = AdminProfile
        fields = ['id', 'user', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserProfile model (regular users).

    The ``user`` and ``created_by`` fields are nested representations
    containing ``id``, ``username``, and ``email`` of the related auth.User
    (or admin's auth.User for ``created_by``).
    """
    user = UserBriefSerializer(read_only=True)
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'created_by', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_created_by(self, obj):
        """Return a brief representation of the admin who created this user."""
        if obj.created_by is None:
            return None
        return {
            'id': obj.created_by.pk,
            'username': obj.created_by.user.username,
            'email': obj.created_by.user.email,
        }



class GroupMemberSerializer(serializers.ModelSerializer):
    """
    Compact serializer for UserProfile when shown inside a group.
    Returns nested user details (id, username, email) instead of just a PK.
    """
    user = UserBriefSerializer(read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'user']


class UserGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserGroup model (groups of regular users).

    ``members`` is a nested list containing each member's ``id`` and
    nested ``user`` details (``id``, ``username``, ``email``).
    ``created_by`` is a nested object with the admin's ``id``, ``username``,
    and ``email``.
    """
    members = GroupMemberSerializer(many=True, read_only=True)
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = UserGroup
        fields = ['id', 'name', 'description', 'created_by', 'members', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_created_by(self, obj):
        """Return a brief representation of the admin who created this group."""
        if obj.created_by is None:
            return None
        return {
            'id': obj.created_by.pk,
            'username': obj.created_by.user.username,
            'email': obj.created_by.user.email,
        }


class DocumentUploadedBySerializer(serializers.ModelSerializer):
    """
    Compact serializer for the UserProfile used in document responses.
    Returns nested user details (id, username, email) instead of just a PK.
    """
    user = UserBriefSerializer(read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'user']


class DocumentShareGroupSerializer(serializers.ModelSerializer):
    """
    Compact serializer for UserGroup when shown inside a document share.
    Returns id, name, and nested member details (id, username, email).
    """
    members = GroupMemberSerializer(many=True, read_only=True)

    class Meta:
        model = UserGroup
        fields = ['id', 'name', 'members']


class DocumentSerializer(serializers.ModelSerializer):
    """
    Serializer for the Document model (uploaded files).

    ``uploaded_by`` is a nested representation containing the uploader's
    ``id`` and nested ``user`` details (``id``, ``username``, ``email``).
    ``group`` is a nested representation with ``id`` and ``name``.
    """
    uploaded_by = DocumentUploadedBySerializer(read_only=True)
    group = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ['id', 'title', 'file', 'uploaded_by', 'group', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

    def get_group(self, obj):
        """Return a brief representation of the associated group, if any."""
        if obj.group is None:
            return None
        return {
            'id': obj.group.pk,
            'name': obj.group.name,
        }


class UploadAndShareSerializer(serializers.Serializer):
    """
    Validates the payload for uploading a new document and immediately
    sharing it with a user or group in a single request.

    Accepts multipart/form-data with:
      - ``title``       – Document title (required)
      - ``file``        – The actual file to upload (required)
      - ``email``       – Email of user to share with (optional; exclusive with group_name)
      - ``group_name``  – Name of group to share with (optional; exclusive with email)

    Exactly one of ``email`` or ``group_name`` must be provided, or neither
    (in which case the document is uploaded but not shared).
    """
    title = serializers.CharField(max_length=255)
    file = serializers.FileField()
    email = serializers.EmailField(required=False)
    group_name = serializers.CharField(required=False)

    def validate(self, attrs):
        email = attrs.get('email')
        group_name = attrs.get('group_name')

        if email and group_name:
            raise serializers.ValidationError(
                'Provide either email or group_name, not both.'
            )

        if email:
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                raise serializers.ValidationError(f"No user found with email '{email}'.")
            user_profile = getattr(user, 'user_profile', None)
            if user_profile is None:
                raise serializers.ValidationError(
                    f"User with email '{email}' does not have a user profile."
                )
            attrs['shared_with_user'] = user_profile

        if group_name:
            try:
                group = UserGroup.objects.get(name=group_name)
            except UserGroup.DoesNotExist:
                raise serializers.ValidationError(f"No group found with name '{group_name}'.")
            attrs['shared_with_group'] = group

        return attrs


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
      ``shared_by`` is a nested representation of the sharer's details
      (``id``, ``user`` → ``id``, ``username``, ``email``).
      ``shared_with_user`` follows the same pattern when set.
      ``shared_with_group`` includes nested member details (id, username, email).
    """
    
    email = serializers.EmailField(write_only=True, required=False)
    group_name = serializers.CharField(write_only=True, required=False)
    shared_by = DocumentUploadedBySerializer(read_only=True)
    shared_with_user = DocumentUploadedBySerializer(read_only=True)
    shared_with_group = DocumentShareGroupSerializer(read_only=True)

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
        
        # Ensure exactly one of ``email`` or ``group_name`` is provided,
        # then resolve it to the appropriate model instance.

        # On success, the validated data will contain either a
        # ``shared_with_user`` (UserProfile) or ``shared_with_group`` (UserGroup)
        # key so that callers can directly use it with ``get_or_create``.
    


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
