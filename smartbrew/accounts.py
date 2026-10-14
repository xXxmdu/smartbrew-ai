"""Accounts, authentication, preference profiles and saved recipes.

Implements Feature 1 (accounts, password and NFC login, preference profiles)
and Feature 8 (saved recipes and one-touch reorder).

Passwords are stored as PBKDF2-HMAC-SHA256 hashes with a per-user random salt.
This is a prototype, but storing clear-text passwords would make the privacy
and security requirements in Part A meaningless.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from .models import Customisation, SavedRecipe, User

PBKDF2_ROUNDS = 120_000


class AuthError(Exception):
    """Raised when authentication fails or an account conflict occurs."""


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Derive a salted hash from a clear-text password.

    Input:
        password (str): The clear-text password.
        salt (str | None): Hex salt to reuse. A fresh 16-byte salt is generated
            when None, which is what registration does.

    Returns:
        tuple[str, str]: (salt_hex, hash_hex).
    """
    salt_hex = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ROUNDS
    )
    return salt_hex, digest.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Check a clear-text password against a stored salt and hash.

    Input:
        password (str): The clear-text password to test.
        salt (str): The stored hex salt.
        expected_hash (str): The stored hex hash.

    Returns:
        bool: True when the password matches. Comparison is constant-time.
    """
    _, candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, expected_hash)


class AccountService:
    """Stores and authenticates the machine's registered users.

    Attributes:
        users: User id mapped to the User record.
    """

    def __init__(self, users: dict[str, User] | None = None) -> None:
        """Create an account service.

        Input:
            users (dict[str, User] | None): Existing users to load, or None for
                an empty machine.

        Returns:
            None.
        """
        self.users: dict[str, User] = users or {}

    def register(
        self,
        user_id: str,
        display_name: str,
        email: str,
        password: str,
        nfc_token: str | None = None,
    ) -> User:
        """Create a new account.

        Input:
            user_id (str): Desired unique login name.
            display_name (str): Name shown in the greeting.
            email (str): Address for e-mail receipts.
            password (str): Clear-text password, at least 6 characters.
            nfc_token (str | None): Optional NFC card identifier to link.

        Returns:
            User: The newly created user.

        Raises:
            AuthError: When the id or NFC token is taken, or the password is
                too short.
        """
        if user_id in self.users:
            raise AuthError(f"User id '{user_id}' is already taken.")
        if len(password) < 6:
            raise AuthError("Password must be at least 6 characters.")
        if nfc_token and self._user_by_nfc(nfc_token):
            raise AuthError("That NFC card is already linked to another account.")

        salt, digest = hash_password(password)
        user = User(
            user_id=user_id,
            display_name=display_name,
            email=email,
            password_salt=salt,
            password_hash=digest,
            nfc_token=nfc_token,
        )
        self.users[user_id] = user
        return user

    def login(self, user_id: str, password: str) -> User:
        """Authenticate a user by id and password.

        Input:
            user_id (str): The login name.
            password (str): The clear-text password.

        Returns:
            User: The authenticated user.

        Raises:
            AuthError: When the id is unknown or the password is wrong. The
                message is deliberately identical in both cases so it cannot be
                used to discover which user ids exist.
        """
        user = self.users.get(user_id)
        if user is None or not verify_password(
            password, user.password_salt, user.password_hash
        ):
            raise AuthError("Incorrect user id or password.")
        return user

    def login_with_nfc(self, nfc_token: str) -> User:
        """Authenticate a user by a single NFC card tap.

        Input:
            nfc_token (str): Identifier read from the card.

        Returns:
            User: The authenticated user.

        Raises:
            AuthError: When no account is linked to that card.
        """
        user = self._user_by_nfc(nfc_token)
        if user is None:
            raise AuthError("This card is not linked to any account.")
        return user

    def _user_by_nfc(self, nfc_token: str) -> User | None:
        """Find the user linked to an NFC token.

        Input:
            nfc_token (str): Identifier read from the card.

        Returns:
            User | None: The matching user, or None when unlinked.
        """
        for user in self.users.values():
            if user.nfc_token and hmac.compare_digest(user.nfc_token, nfc_token):
                return user
        return None

    def set_preferences(self, user: User, preferences: Customisation) -> User:
        """Replace a user's default customisation.

        Input:
            user (User): The account to update.
            preferences (Customisation): The new defaults.

        Returns:
            User: The updated user.
        """
        user.preferences = preferences
        return user

    def save_recipe(
        self, user: User, name: str, drink_key: str, customisation: Customisation
    ) -> SavedRecipe:
        """Store a named recipe on a user's profile.

        An existing recipe with the same name is overwritten, which is how
        "modify" is expressed.

        Input:
            user (User): The owning account.
            name (str): Customer-chosen recipe name.
            drink_key (str): Key of the base drink.
            customisation (Customisation): Configuration to store.

        Returns:
            SavedRecipe: The stored recipe.

        Raises:
            ValueError: When the name is blank.
        """
        clean = name.strip()
        if not clean:
            raise ValueError("A recipe name is required.")
        recipe = SavedRecipe(name=clean, drink_key=drink_key,
                             customisation=customisation)
        user.saved_recipes[clean] = recipe
        return recipe

    def delete_recipe(self, user: User, name: str) -> bool:
        """Remove a named recipe from a user's profile.

        Input:
            user (User): The owning account.
            name (str): Recipe name to remove.

        Returns:
            bool: True when a recipe was removed, False when none matched.
        """
        return user.saved_recipes.pop(name.strip(), None) is not None

    def to_dict(self) -> dict:
        """Convert all accounts to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: User id mapped to the user's dictionary form.
        """
        return {k: v.to_dict() for k, v in self.users.items()}

    @staticmethod
    def from_dict(raw: dict) -> "AccountService":
        """Rebuild an AccountService from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            AccountService: The reconstructed service.
        """
        return AccountService({k: User.from_dict(v) for k, v in raw.items()})
