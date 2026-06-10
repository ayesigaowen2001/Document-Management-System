from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import AdminProfile, Document, UserGroup, UserProfile


User = get_user_model()


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
        read_only_fields = ['id', 'uploaded_at']


class AccountCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
