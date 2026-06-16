# =============================================================================
# DMS/Document_Management_System/models.py — Data Models
# =============================================================================
# This module defines all database models for the Document Management System.
#
# Models:
# - AdminProfile  – Extends Django User for admin-level functionality.
# - UserProfile   – Represents a regular (non-admin) application user.
# - UserGroup     – A group of UserProfiles, created and managed by admins.
# - Document      – An uploaded file owned by a UserProfile.
# - DocumentShare – Tracks sharing of documents with users or groups.
# - SessionToken  – Session-based auth token (one per login, multi-session support)
#
# Relationships:
#   AdminProfile (1:1) User  ── creates ──→ UserGroup, UserProfile
#   UserProfile  (1:1) User  ── uploads ──→ Document
#   DocumentShare ──→ Document + UserProfile|UserGroup
#   SessionToken (M:1) User  ── one token per session
# =============================================================================

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone



User = get_user_model()


class AdminProfile(models.Model):
	"""
	Profile representing an administrative user of the system.

	An AdminProfile is linked one-to-one with a Django User that must have
	is_staff=True or is_superuser=True.  It provides convenience methods for
	creating users, groups, and managing group membership — all validated
	against ownership.

	Fields
	------
	user       : OneToOneField → User (required, must be staff/superuser)
	created_at : DateTimeField, auto-set on creation
	"""
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.user.get_username()

	def save(self, *args, **kwargs):
		"""
		Enforce that only staff or superuser users can have an AdminProfile.
		Raises PermissionDenied otherwise.
		"""
		if not (self.user.is_staff or self.user.is_superuser):
			raise PermissionDenied('Only staff/superusers can be admin profiles.')
		super().save(*args, **kwargs)

	def create_user(self, username, email=None, password=None):
		"""
		Create a new regular Django user and its associated UserProfile,
		with this admin as the creator.
		"""
		user = User.objects.create_user(
			username=username,
			email=email,
			password=password,
			#**extra_fields,
		)
		return UserProfile.objects.create(user=user, created_by=self)

	def create_group(self, name, description=''):
		"""
		Create a new UserGroup owned by this admin.
		"""
		return UserGroup.objects.create(name=name, description=description, created_by=self)

	def add_user_to_group(self, user_profile, group):
		"""
		Add a UserProfile to a UserGroup.
		Only allowed if this admin owns (created) the group.
		"""
		if self.pk is None or group.created_by_id != self.pk:
			raise PermissionDenied('You can only manage groups you created.')
		group.members.add(user_profile)
		return group


class UserProfile(models.Model):
	"""
	Profile representing a regular (non-admin) user of the system.

	A UserProfile is linked one-to-one with a Django User and optionally
	records which AdminProfile created it.

	Fields
	------
	user       : OneToOneField → User (required)
	created_by : ForeignKey → AdminProfile (nullable, set on creation)
	created_at : DateTimeField, auto-set on creation
	"""
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
	"""
	A named group of UserProfiles, created by an AdminProfile.

	Groups are used to simplify document sharing — sharing a document with
	a group grants access to all its members.

	Fields
	------
	name        : CharField (unique, max 120 chars)
	description : TextField (optional)
	created_by  : ForeignKey → AdminProfile (required, protected from delete)
	members     : ManyToManyField → UserProfile (optional)
	created_at  : DateTimeField, auto-set on creation
	"""
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
	"""
	An uploaded document file in the system.

	Each document is owned by a UserProfile (the uploader) and may optionally
	be associated with a UserGroup.  Custom permissions (share_document) are
	defined via the Meta class.

	Fields
	------
	title       : CharField (max 255)
	file        : FileField (uploaded to 'documents/' directory)
	uploaded_by : ForeignKey → UserProfile (required)
	group       : ForeignKey → UserGroup (nullable)
	uploaded_at : DateTimeField, auto-set on creation
	"""
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
		permissions = [
			('share_document', 'Can share document'),
		]

	def __str__(self):
		return self.title


class DocumentShare(models.Model):
	"""
	Records a document sharing relationship.

	A share targets either a single UserProfile OR a UserGroup (enforced by
	a CheckConstraint).  Unique constraints prevent duplicate shares for the
	same document+user or document+group combination.

	Fields
	------
	document           : ForeignKey → Document (required)
	shared_by          : ForeignKey → UserProfile (the sharer)
	shared_with_user   : ForeignKey → UserProfile (nullable, exclusive with group)
	shared_with_group  : ForeignKey → UserGroup     (nullable, exclusive with user)
	created_at         : DateTimeField, auto-set on creation
	"""
	document = models.ForeignKey(
		Document,
		on_delete=models.CASCADE,
		related_name='shares',
	)
	shared_by = models.ForeignKey(
		UserProfile,
		on_delete=models.CASCADE,
		related_name='shared_documents',
	)
	shared_with_user = models.ForeignKey(
		UserProfile,
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name='received_document_shares',
	)
	shared_with_group = models.ForeignKey(
		UserGroup,
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name='received_document_shares',
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			# Ensure exactly one of {shared_with_user, shared_with_group} is set.
			models.CheckConstraint(
				condition=(
					(models.Q(shared_with_user__isnull=False) & models.Q(shared_with_group__isnull=True))
					| (models.Q(shared_with_user__isnull=True) & models.Q(shared_with_group__isnull=False))
				),
				name='document_share_single_target',
			),
			# Prevent duplicate user shares for the same document.
			models.UniqueConstraint(
				fields=['document', 'shared_with_user'],
				condition=models.Q(shared_with_user__isnull=False),
				name='unique_document_share_user',
			),
			# Prevent duplicate group shares for the same document.
			models.UniqueConstraint(
				fields=['document', 'shared_with_group'],
				condition=models.Q(shared_with_group__isnull=False),
				name='unique_document_share_group',
			),
		]
		ordering = ['-created_at']

	def __str__(self):
		target = self.shared_with_user or self.shared_with_group
		return f'{self.document} -> {target}'


class SessionToken(models.Model):
	"""
	A session-based token tied to a specific user session.

	Each time a user logs in, a new SessionToken is created.  Multiple
	simultaneous sessions are supported (each has its own token).

	Fields
	------
	user       : ForeignKey → User (multiple tokens per user allowed)
	key        : CharField (unique, 40-char hex, auto-generated)
	created_at : DateTimeField (auto-set on creation)
	expires_at : DateTimeField (nullable; set if SESSION_TOKEN_EXPIRE_HOURS defined)
	"""
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='session_tokens',
	)
	key = models.CharField(
		max_length=40,
		unique=True,
		editable=False,
	)
	created_at = models.DateTimeField(auto_now_add=True, db_index=True)
	expires_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		db_table = 'session_tokens'
		ordering = ['-created_at']

	def __str__(self) -> str:
		return f'{self.user} [{self.key[:12]}...]'

	def save(self, *args, **kwargs):
		"""Auto-generate key and set expires_at based on settings when first created."""
		if self._state.adding:
			if not self.key:
				self.key = secrets.token_hex(20)
			if self.expires_at is None:
				hours = getattr(settings, 'SESSION_TOKEN_EXPIRE_HOURS', None)
				if hours is not None:
					self.expires_at = timezone.now() + timedelta(hours=int(hours))
		super().save(*args, **kwargs)

	@property
	def is_expired(self) -> bool:
		"""Check whether this token has expired."""
		if self.expires_at is None:
			return False
		return timezone.now() >= self.expires_at

	@classmethod
	def clean_expired(cls):
		"""Delete all expired tokens.  Call periodically from a cron / celery task."""
		cls.objects.filter(expires_at__isnull=False, expires_at__lte=timezone.now()).delete()


