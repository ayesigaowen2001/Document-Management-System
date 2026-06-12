# Refactoring Plan: Simplify DMS Models

## Current Problem

The database has **two separate profile tables** (`AdminProfile` and `UserProfile`) that both do essentially the same thing — extend `auth_user` with extra metadata. This creates cascading complexity:

| Area               | Current                                                       | Problem                                                                                       |
| ------------------ | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **models.py**      | 2 models (AdminProfile, UserProfile) + UserGroup              | Nearly identical structure                                                                    |
| **views.py**       | Heavy `hasattr()` checks everywhere                           | `is_admin_actor()` checks `hasattr(user, 'admin_profile')` vs `hasattr(user, 'user_profile')` |
| **serializers.py** | 2 serializers (AdminProfileSerializer, UserProfileSerializer) | Duplicate code                                                                                |
| **admin.py**       | 2 admin registrations                                         | Duplicate                                                                                     |
| **Database**       | 2 profile tables with near-identical columns                  | Redundant storage                                                                             |

## Proposed Solution

### 1. Collapse `AdminProfile` + `UserProfile` → Single `Profile` model

```python
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    created_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_profiles')
    created_at = models.DateTimeField(auto_now_add=True)
```

**Why this works:** Django's `auth_user` already has `is_staff`, `is_superuser`, `is_active` — so there's no reason to split profiles by role. A single `Profile` tracks:

- Who the user is (`user` FK)
- Who created them (`created_by` — nullable FK to another Profile)
- When (`created_at`)

### 2. Simplify `UserGroup`

Current `UserGroup.members` is a `ManyToManyField(UserProfile)`. After the change, it becomes:

```python
members = models.ManyToManyField(Profile, related_name='groups', blank=True)
```

And `created_by` becomes `ForeignKey(Profile, ...)`.

If you want, we could also integrate with Django's `auth_group` — but that's optional. Keeping it custom is fine for document-sharing purposes.

### 3. Update all related files

| File                    | What Changes                                                                                              | Impact               |
| ----------------------- | --------------------------------------------------------------------------------------------------------- | -------------------- |
| **models.py**           | Replace AdminProfile + UserProfile with single Profile                                                    | -2 models, less code |
| **serializers.py**      | Remove AdminProfileSerializer + UserProfileSerializer → single ProfileSerializer                          | Less code            |
| **views.py**            | Remove `is_admin_actor()`, simplify permission checks to use `user.is_staff`/`user.is_superuser` directly | Much simpler         |
| **admin.py**            | Single ProfileAdmin instead of two                                                                        | Less code            |
| **Database migrations** | Create Profile table, migrate data, drop old tables                                                       | One-time migration   |

### 4. Key changes in views.py logic

**Before (current):**

```python
def is_admin_actor(user) -> bool:
    return bool(user.is_superuser or getattr(user, 'is_staff', False) or hasattr(user, 'admin_profile'))

# In DocumentAccessPermission:
if is_admin_actor(user):
    return True
```

**After (simplified):**

```python
# No helper function needed. Just use:
if user.is_staff or user.is_superuser:
    return True
```

This is **clearer** because `is_staff` already means "admin" in Django.

### 5. What stays the same

- **Document** model — no changes needed
- **DocumentShare** model — just FK changes from `UserProfile` → `Profile`
- **Auth endpoints** (AuthTokenLoginView, AuthTokenLogoutView) — no change
- **Permission management** — no change

## Trade-offs

| 👍 Pros                    | 👎 Cons                                    |
| -------------------------- | ------------------------------------------ |
| ~40% less code in views.py | Must run data migration                    |
| No `hasattr` checks        | All serializers/views touch the same model |
| Cleaner DB schema          | Learning curve (one profile vs two)        |
| Easier to extend later     |                                            |
| Standard Django pattern    |                                            |

---

**Ready? Say "Implement it" and I'll make all the changes.**
