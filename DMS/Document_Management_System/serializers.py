# This file defines the serializers for the Document Management System (DMS) application.
# It includes serializers for admin profiles, user profiles, user groups, and documents.
# Each serializer specifies the fields to be included in the API responses and any validation rules for creating or updating instances of the models. 
# The AccountCreateSerializer is used for validating data when creating new user accounts, ensuring that the required fields are provided and meet the specified criteria.
from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import AdminProfile, Document, DocumentShare, UserGroup, UserProfile


User = get_user_model()

DOCUMENT_PERMISSION_CHOICES = [
    'view_document',
    'add_document',
    'change_document',
    'delete_document',
    'share_document',
]


class AdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminProfile
        fields = ['id', 'user', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'created_by', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserGroup
        fields = ['id', 'name', 'description', 'created_by', 'members', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserGroupAddMemberSerializer(serializers.Serializer):
    user_profile_id = serializers.PrimaryKeyRelatedField(
        queryset=UserProfile.objects.all(),
        source='user_profile',
    )


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'title', 'file', 'uploaded_by', 'group', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at', 'uploaded_by']


class DocumentShareSerializer(serializers.ModelSerializer):
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
        shared_with_user = attrs.get('shared_with_user')
        shared_with_group = attrs.get('shared_with_group')

        if bool(shared_with_user) == bool(shared_with_group):
            raise serializers.ValidationError('Provide either shared_with_user or shared_with_group.')

        return attrs


class DocumentPermissionAssignmentSerializer(serializers.Serializer):
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source='user')
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=DOCUMENT_PERMISSION_CHOICES),
        allow_empty=False,
    )


class UserUpdateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True, min_length=8, required=False)


class AccountCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
