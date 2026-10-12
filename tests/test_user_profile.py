from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import UserProfile


class UserProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="pass12345")

    def test_profile_is_reachable_from_user(self):
        UserProfile.objects.create(user=self.user, rating=1200)
        self.assertEqual(self.user.profile.rating, 1200)

    def test_rating_out_of_range_is_invalid(self):
        profile = UserProfile(user=self.user, rating=99999)
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_rating_is_optional(self):
        profile = UserProfile(user=self.user)
        profile.full_clean()  # should not raise