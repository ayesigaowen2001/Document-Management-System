
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import models


User = get_user_model()


class AdminProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.user.get_username()

	def save(self, *args, **kwargs):
		if not (self.user.is_staff or self.user.is_superuser):
			raise PermissionDenied('Only staff/superusers can be admin profiles.')
		super().save(*args, **kwargs)

	def create_user(self, username, email=None, password=None, **extra_fields):
		user = User.objects.create_user(
			username=username,
			email=email,
			password=password,
			**extra_fields,
		)
		return UserProfile.objects.create(user=user, created_by=self)

	def create_group(self, name, description=''):
		return UserGroup.objects.create(name=name, description=description, created_by=self)

	def add_user_to_group(self, user_profile, group):
		if self.pk is None or group.created_by_id != self.pk:
			raise PermissionDenied('You can only manage groups you created.')
		group.members.add(user_profile)
		return group


class UserProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='user_profile')
	created_by = models.ForeignKey(
		AdminProfile,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='created_users',
	)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.user.get_username()


class UserGroup(models.Model):
	name = models.CharField(max_length=120, unique=True)
	description = models.TextField(blank=True)
	created_by = models.ForeignKey(
		AdminProfile,
		on_delete=models.PROTECT,
		related_name='groups',
	)
	members = models.ManyToManyField(UserProfile, related_name='groups', blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.name


class Document(models.Model):
	title = models.CharField(max_length=255)
	file = models.FileField(upload_to='documents/')
	uploaded_by = models.ForeignKey(
		UserProfile,
		on_delete=models.CASCADE,
		related_name='documents',
	)
	group = models.ForeignKey(
		UserGroup,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='documents',
	)
	uploaded_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-uploaded_at']

	def __str__(self):
		return self.title
