import base64
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from easy_reels.licensing import LicenseClientConfig, LicenseManager, LicenseStore


def _token(private_key: Ed25519PrivateKey, device_id: str, product: str) -> str:
    payload = json.dumps(
        {
            "v": 1,
            "perpetual": True,
            "product": product,
            "device_id": device_id,
            "license_id": str(uuid.uuid4()),
            "issued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    signature = private_key.sign(payload)
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    return f"{encode(payload)}.{encode(signature)}"


def test_old_license_is_migrated_to_user_store(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    device_id = "a" * 64
    product = "easy-reels-generator"
    token = _token(private_key, device_id, product)
    legacy_path = tmp_path / "portable" / "licenses" / "license.json"
    new_path = tmp_path / "user-data" / "license.json"
    LicenseStore(legacy_path).write_token(token)

    manager = LicenseManager(
        LicenseClientConfig(
            activation_url="https://example.invalid/activate",
            product=product,
            public_key=base64.b64encode(public_key).decode("ascii"),
        ),
        new_path,
        app_version="0.8.0",
        device_id=device_id,
        legacy_license_paths=(legacy_path,),
    )

    result = manager.check()

    assert result.valid is True
    assert new_path.is_file()
    assert LicenseStore(new_path).read_token() == token
