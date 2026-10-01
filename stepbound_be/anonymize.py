"""Players are known by a keyed hash of the random id their phone made.

The id is random (the app makes it at first launch, and a new one when the
player turns sending off and on again): it says nothing about the phone or
the person. Hashing it with a server-side secret means the database alone
cannot even be matched against a phone."""

from __future__ import annotations

import hashlib
import hmac


def player_hash(install_id: str, pepper: str) -> str:
    return hmac.new(
        pepper.encode("utf-8"), install_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()
