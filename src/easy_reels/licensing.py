from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import certifi
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .subprocess_utils import hidden_process_kwargs

from .errors import (
    LicenseActivationError,
    LicenseConfigurationError,
    LicenseValidationError,
)


TOKEN_VERSION = 1
STORE_VERSION = 1
FINGERPRINT_NAMESPACE = "proai.easy-reels-generator.device.v1"
LICENSE_KEY_RE = re.compile(r"^ERG(?:-[A-Z2-9]{4}){4}$")
DEVICE_ID_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class LicenseClientConfig:
    activation_url: str
    product: str
    public_key: str
    timeout_seconds: int = 15


@dataclass(frozen=True, slots=True)
class VerifiedLicense:
    license_id: str
    device_id: str
    issued_at: datetime
    product: str


@dataclass(frozen=True, slots=True)
class LicenseCheck:
    valid: bool
    code: str
    message: str
    license: VerifiedLicense | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    actual = value or utc_now()
    return actual.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise LicenseValidationError("Файл лицензии имеет неверный формат.") from exc


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise LicenseValidationError("В лицензии отсутствует дата активации.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LicenseValidationError("В лицензии указана неверная дата активации.") from exc
    if parsed.tzinfo is None:
        raise LicenseValidationError("В лицензии указана неверная дата активации.")
    return parsed.astimezone(timezone.utc)


def normalize_license_key(value: str) -> str:
    normalized = value.strip().upper().replace("–", "-").replace("—", "-")
    normalized = re.sub(r"\s+", "", normalized)
    if not LICENSE_KEY_RE.fullmatch(normalized):
        raise LicenseActivationError(
            "Проверьте ключ. Формат: ERG-XXXX-XXXX-XXXX-XXXX.",
            code="invalid_key_format",
        )
    return normalized


def _windows_machine_guid() -> str | None:
    try:
        import winreg

        access = winreg.KEY_READ
        if hasattr(winreg, "KEY_WOW64_64KEY"):
            access |= winreg.KEY_WOW64_64KEY
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            access,
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "MachineGuid")
        return str(value).strip() or None
    except (ImportError, OSError):
        return None


def _mac_platform_uuid() -> str | None:
    try:
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
            **hidden_process_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout)
    return match.group(1).strip() if match else None


def _linux_machine_id() -> str | None:
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return None


def raw_machine_identifier(system: str | None = None) -> tuple[str, str]:
    system_name = system or platform.system()
    if system_name == "Windows":
        value = _windows_machine_guid()
    elif system_name == "Darwin":
        value = _mac_platform_uuid()
    elif system_name == "Linux":
        value = _linux_machine_id()
    else:
        value = None
    if not value:
        value = f"{uuid.getnode():012x}|{socket.gethostname()}|{platform.machine()}"
    return system_name, value


def device_fingerprint(
    *, raw_identifier: str | None = None, system: str | None = None
) -> str:
    if raw_identifier is None:
        system_name, raw_identifier = raw_machine_identifier(system)
    else:
        system_name = system or platform.system()
    material = (
        FINGERPRINT_NAMESPACE
        + "\0"
        + system_name.casefold().strip()
        + "\0"
        + raw_identifier.casefold().strip()
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def load_client_config(path: str | Path) -> LicenseClientConfig:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LicenseConfigurationError("Не найден файл настройки лицензии.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise LicenseConfigurationError(
            "Не удалось прочитать настройку лицензии."
        ) from exc
    try:
        activation_url = str(data["activation_url"]).strip()
        product = str(data["product"]).strip()
        public_key = str(data["public_key"]).strip()
        timeout_seconds = int(data.get("timeout_seconds", 15))
    except (KeyError, TypeError, ValueError) as exc:
        raise LicenseConfigurationError("Файл настройки лицензии заполнен неверно.") from exc
    if not activation_url.startswith("https://"):
        raise LicenseConfigurationError("Адрес сервера активации должен использовать HTTPS.")
    if not product or not 3 <= timeout_seconds <= 60:
        raise LicenseConfigurationError("Файл настройки лицензии заполнен неверно.")
    try:
        raw_key = base64.b64decode(public_key, validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise LicenseConfigurationError("Публичный ключ лицензии имеет неверный формат.") from exc
    if len(raw_key) != 32:
        raise LicenseConfigurationError("Публичный ключ лицензии имеет неверный формат.")
    return LicenseClientConfig(
        activation_url=activation_url,
        product=product,
        public_key=public_key,
        timeout_seconds=timeout_seconds,
    )


class LicenseTokenVerifier:
    def __init__(self, public_key_b64: str, product: str):
        try:
            raw = base64.b64decode(public_key_b64, validate=True)
            self.public_key = Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, UnicodeEncodeError) as exc:
            raise LicenseConfigurationError(
                "Публичный ключ лицензии имеет неверный формат."
            ) from exc
        self.product = product

    def verify(self, token: str, device_id: str) -> VerifiedLicense:
        parts = token.split(".")
        if len(parts) != 2:
            raise LicenseValidationError("Файл лицензии имеет неверный формат.")
        payload_raw = _b64url_decode(parts[0])
        signature = _b64url_decode(parts[1])
        try:
            self.public_key.verify(signature, payload_raw)
        except InvalidSignature as exc:
            raise LicenseValidationError(
                "Подпись лицензии недействительна. Выполните активацию снова."
            ) from exc
        try:
            payload = json.loads(payload_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LicenseValidationError("Файл лицензии имеет неверный формат.") from exc
        if payload.get("v") != TOKEN_VERSION or payload.get("perpetual") is not True:
            raise LicenseValidationError("Версия лицензии не поддерживается.")
        if payload.get("product") != self.product:
            raise LicenseValidationError("Лицензия выпущена для другого продукта.")
        token_device = payload.get("device_id")
        if not isinstance(token_device, str) or not DEVICE_ID_RE.fullmatch(token_device):
            raise LicenseValidationError("В лицензии указан неверный идентификатор устройства.")
        if not isinstance(device_id, str) or not DEVICE_ID_RE.fullmatch(device_id):
            raise LicenseValidationError("Не удалось определить это устройство.")
        if token_device != device_id:
            raise LicenseValidationError(
                "Лицензия привязана к другому устройству. Для переноса обратитесь к продавцу."
            )
        license_id = payload.get("license_id")
        try:
            uuid.UUID(str(license_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise LicenseValidationError("В лицензии отсутствует её идентификатор.") from exc
        issued_at = _parse_time(payload.get("issued_at"))
        now = utc_now()
        if (issued_at - now).total_seconds() > 86400:
            raise LicenseValidationError("Дата лицензии значительно опережает системное время.")
        return VerifiedLicense(
            license_id=str(license_id),
            device_id=token_device,
            issued_at=issued_at,
            product=self.product,
        )


class LicenseStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read_token(self) -> str | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise LicenseValidationError(
                "Не удалось прочитать локальный файл лицензии."
            ) from exc
        if data.get("format") != STORE_VERSION or not isinstance(data.get("token"), str):
            raise LicenseValidationError("Локальный файл лицензии имеет неверный формат.")
        return data["token"]

    def write_token(self, token: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        body = {
            "format": STORE_VERSION,
            "token": token,
            "activated_at": iso_utc(),
        }
        try:
            temp.write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            try:
                os.chmod(temp, 0o600)
            except OSError:
                pass
            os.replace(temp, self.path)
        except OSError as exc:
            raise LicenseActivationError(
                "Не удалось сохранить активацию в защищённой папке пользователя."
            ) from exc
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass


class LicenseManager:
    def __init__(
        self,
        config: LicenseClientConfig,
        license_path: str | Path,
        *,
        app_version: str,
        device_id: str | None = None,
        legacy_license_paths: tuple[str | Path, ...] = (),
        log_path: str | Path | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ):
        self.config = config
        self.store = LicenseStore(license_path)
        self.device_id = device_id or device_fingerprint()
        self.app_version = app_version
        self.legacy_stores = [LicenseStore(path) for path in legacy_license_paths]
        self.log_path = Path(log_path) if log_path else None
        self.ssl_context = ssl_context or ssl.create_default_context(
            cafile=certifi.where()
        )
        self.verifier = LicenseTokenVerifier(config.public_key, config.product)

    def check(self) -> LicenseCheck:
        try:
            token = self.store.read_token()
            legacy_store = None
            if token is None:
                for candidate in self.legacy_stores:
                    token = candidate.read_token()
                    if token is not None:
                        legacy_store = candidate
                        break
            if token is None:
                return LicenseCheck(False, "not_activated", "Программа ещё не активирована.")
            verified = self.verifier.verify(token, self.device_id)
        except LicenseValidationError as exc:
            return LicenseCheck(False, "invalid_license", str(exc))
        if legacy_store is not None:
            try:
                self.store.write_token(token)
            except LicenseActivationError as exc:
                self._write_diagnostic("Не удалось перенести старую лицензию", exc)
        return LicenseCheck(True, "active", "Лицензия активна · бессрочно", verified)

    def activate(self, key: str) -> LicenseCheck:
        normalized_key = normalize_license_key(key)
        body = {
            "license_key": normalized_key,
            "device_id": self.device_id,
            "product": self.config.product,
            "app_version": self.app_version,
            "platform": f"{platform.system()} {platform.release()}",
        }
        request = urllib.request.Request(
            self.config.activation_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": f"EasyReelsGenerator/{self.app_version}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.timeout_seconds,
                context=self.ssl_context,
            ) as response:
                response_body = response.read(1024 * 1024)
        except urllib.error.HTTPError as exc:
            response_body = exc.read(1024 * 1024)
            self._raise_server_error(response_body, fallback=f"Ошибка сервера: {exc.code}.")
        except urllib.error.URLError as exc:
            self._write_diagnostic("Ошибка HTTPS-запроса активации", exc)
            reason = exc.reason
            if isinstance(reason, ssl.SSLCertVerificationError):
                message = (
                    "Не удалось проверить защищённое соединение с сервером активации. "
                    "Проверьте дату и время на компьютере и повторите попытку."
                )
                code = "ssl_certificate_error"
            elif isinstance(reason, (TimeoutError, socket.timeout)):
                message = "Сервер активации не ответил вовремя. Повторите попытку."
                code = "network_timeout"
            else:
                message = (
                    "Не удалось связаться с сервером активации. "
                    "Проверьте интернет и повторите попытку."
                )
                code = "network_error"
            raise LicenseActivationError(
                message,
                code=code,
            ) from exc
        except (ssl.SSLError, TimeoutError, OSError) as exc:
            self._write_diagnostic("Ошибка соединения с сервером активации", exc)
            raise LicenseActivationError(
                "Не удалось связаться с сервером активации. "
                "Подробности записаны в журнал activation.log.",
                code="network_error",
            ) from exc
        try:
            response_data = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LicenseActivationError(
                "Сервер активации вернул непонятный ответ.", code="bad_response"
            ) from exc
        token = response_data.get("token")
        if response_data.get("ok") is not True or not isinstance(token, str):
            self._raise_server_error(response_body, fallback="Активация не выполнена.")
        try:
            verified = self.verifier.verify(token, self.device_id)
        except LicenseValidationError as exc:
            raise LicenseActivationError(
                f"Сервер вернул недействительную лицензию: {exc}",
                code="invalid_server_token",
            ) from exc
        self.store.write_token(token)
        return LicenseCheck(True, "active", "Лицензия активна · бессрочно", verified)

    def _write_diagnostic(self, title: str, exc: BaseException) -> None:
        if self.log_path is None:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            line = f"{iso_utc()} | {title}: {type(exc).__name__}: {exc}\n"
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass

    @staticmethod
    def _raise_server_error(response_body: bytes, *, fallback: str) -> None:
        try:
            data = json.loads(response_body.decode("utf-8"))
            error = data.get("error", {})
            message = str(error.get("message") or fallback)
            code = str(error.get("code") or "activation_failed")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            message = fallback
            code = "activation_failed"
        raise LicenseActivationError(message, code=code)
