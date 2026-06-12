# =============================================================================
# DMS/Document_Management_System/serializers.py — Serializers
# =============================================================================
# This module defines all DRF serializers for the Document Management System.
#
# Serializers are categorised as follows:
#
# Model serializers (directly mirror database models):
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

    Validates that exactly one of `shared_with_user` or `shared_with_group`
    is provided (enforced in validate()).
    """
    class Meta:
        model = DocumentShare
        fields = [
            'id',
            'document',
            'shared_by',
            'shared_with_user',
            'shared_with_group',
            'created_at',
        ]
        read_only_fields = ['id', 'document', 'shared_by', 'created_at']

    def validate(self, attrs):
        """
        Ensure that exactly one of shared_with_user / shared_with_group is set.
        """
        shared_with_user = attrs.get('shared_with_user')
        shared_with_group = attrs.get('shared_with_group')

        if bool(shared_with_user) == bool(shared_with_group):
            raise serializers.ValidationError('Provide either shared_with_user or shared_with_group.')

        return attrs


# ---------------------------------------------------------------------------
# Non-model (input-validation) serializers
# ---------------------------------------------------------------------------

class UserGroupAddMemberSerializer(serializers.Serializer):
    """
    Validates the payload for adding a user to a group.
    Accepts a single `user_profile_id` (PK of the UserProfile to add).
    """
    user_profile_id = serializers.PrimaryKeyRelatedField(
        queryset=UserProfile.objects.all(),
        source='user_profile',
    )


class DocumentPermissionAssignmentSerializer(serializers.Serializer):
    """
    Validates the payload for assigning document permissions to a user.
    Accepts:
      - user_id      : PK of the target User
      - permissions  : non-empty list of permission codenames
    """
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source='user')
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=DOCUMENT_PERMISSION_CHOICES),
        allow_empty=False,
    )


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
