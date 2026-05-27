"""BulutKlinik API connector.

Resmi API: https://api.bulutklinik.com
Auth akisi:
    POST /api/v3/general/connectApi   -> access_token + refresh_token
    POST /api/v3/general/refreshApi   -> yeni access_token
    POST /api/v3/general/disconnectApi

Bu modul stdlib + 'requests' kullanir (requirements.txt'de zaten var).
Token'lar bellekte cache edilir; saklama yazklinik_web tarafinda settings DB
uzerinden yapilir (get_credentials/save_credentials sarmalayicilari).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

import requests


DEFAULT_BASE_URL = "https://api.bulutklinik.com"
DEFAULT_TIMEOUT = 15.0
TOKEN_REFRESH_GRACE = 60  # access_token suresi dolmadan bu kadar saniye kala yenile

CREDENTIAL_KEYS = (
    "api_client_id",
    "api_secret_key",
    "api_user_name",
    "api_user_password",
)


class BulutklinikError(Exception):
    """Generic API error. Bir HTTP cevabi varsa .status_code/.payload doludur."""

    def __init__(self, message: str, status_code: int = 0, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class BulutklinikAuthError(BulutklinikError):
    pass


@dataclass
class BulutklinikCredentials:
    api_client_id: str = ""
    api_secret_key: str = ""
    api_user_name: str = ""
    api_user_password: str = ""
    base_url: str = DEFAULT_BASE_URL

    def is_complete(self) -> bool:
        return all(
            str(getattr(self, k) or "").strip()
            for k in CREDENTIAL_KEYS
        )

    def to_safe_dict(self) -> Dict[str, str]:
        def _mask(value: str) -> str:
            text = str(value or "")
            if not text:
                return ""
            if len(text) <= 6:
                return "*" * len(text)
            return text[:3] + "..." + text[-3:]

        return {
            "api_client_id": self.api_client_id,
            "api_secret_key_masked": _mask(self.api_secret_key),
            "api_user_name": self.api_user_name,
            "api_user_password_masked": _mask(self.api_user_password),
            "base_url": self.base_url or DEFAULT_BASE_URL,
            "configured": self.is_complete(),
        }


@dataclass
class _TokenState:
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0  # epoch seconds; 0 = bilinmiyor
    raw: Dict[str, Any] = field(default_factory=dict)


class BulutklinikClient:
    """Thread-safe minimal client. Tek bir doktor/klinik baglamiyla calisir."""

    def __init__(
        self,
        credentials: BulutklinikCredentials,
        timeout: float = DEFAULT_TIMEOUT,
        session: Optional[requests.Session] = None,
    ):
        self.credentials = credentials
        self.timeout = float(timeout or DEFAULT_TIMEOUT)
        self.session = session or requests.Session()
        self._token = _TokenState()
        self._lock = threading.RLock()

    # ----- helpers -----

    @property
    def base_url(self) -> str:
        return (self.credentials.base_url or DEFAULT_BASE_URL).rstrip("/")

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.base_url + ("" if path.startswith("/") else "/") + path

    @staticmethod
    def _envelope_error(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        for key in ("errorMessage", "error_message", "message", "errorType"):
            value = payload.get(key)
            if value:
                return str(value)
        return ""

    @staticmethod
    def _envelope_data(payload: Any) -> Any:
        if isinstance(payload, dict):
            if "data" in payload:
                return payload.get("data")
        return payload

    def _parse_token_payload(self, payload: Any) -> _TokenState:
        data = self._envelope_data(payload) if isinstance(payload, dict) else {}
        access = ""
        refresh = ""
        expires_in = 0
        sources = [data, payload if isinstance(payload, dict) else {}]
        for src in sources:
            if not isinstance(src, dict):
                continue
            access = access or str(
                src.get("access_token") or src.get("accessToken") or "")
            refresh = refresh or str(
                src.get("refresh_token") or src.get("refreshToken") or "")
            ttl = src.get("expires_in") or src.get("expiresIn")
            if ttl and not expires_in:
                try:
                    expires_in = int(float(ttl))
                except Exception:
                    expires_in = 0
        if not access:
            err = self._envelope_error(payload) or "access_token alinamadi"
            raise BulutklinikAuthError(err, payload=payload)
        expires_at = time.time() + max(0, expires_in - TOKEN_REFRESH_GRACE) if expires_in else 0
        return _TokenState(
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            raw=payload if isinstance(payload, dict) else {},
        )

    # ----- auth -----

    def login(self) -> _TokenState:
        if not self.credentials.is_complete():
            raise BulutklinikAuthError("Credentials eksik")
        url = self._url("/api/v3/general/connectApi")
        body = {
            "apiClientId": self.credentials.api_client_id,
            "apiSecretKey": self.credentials.api_secret_key,
            "apiUserName": self.credentials.api_user_name,
            "apiUserPassword": self.credentials.api_user_password,
        }
        try:
            resp = self.session.post(url, json=body, timeout=self.timeout)
        except requests.RequestException as ex:
            raise BulutklinikAuthError(f"Baglanti hatasi: {ex}") from ex
        payload: Any
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw_text": resp.text[:500]}
        if resp.status_code >= 400:
            err = self._envelope_error(payload) or f"HTTP {resp.status_code}"
            raise BulutklinikAuthError(err, status_code=resp.status_code, payload=payload)
        token = self._parse_token_payload(payload)
        with self._lock:
            self._token = token
        return token

    def refresh(self) -> _TokenState:
        with self._lock:
            refresh_token = self._token.refresh_token
        if not refresh_token:
            return self.login()
        url = self._url("/api/v3/general/refreshApi")
        body = {"refresh_token": refresh_token}
        try:
            resp = self.session.post(url, json=body, timeout=self.timeout)
        except requests.RequestException as ex:
            raise BulutklinikAuthError(f"Refresh hata: {ex}") from ex
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw_text": resp.text[:500]}
        if resp.status_code >= 400:
            return self.login()
        token = self._parse_token_payload(payload)
        with self._lock:
            if not token.refresh_token:
                token.refresh_token = refresh_token
            self._token = token
        return token

    def logout(self) -> bool:
        with self._lock:
            access = self._token.access_token
            self._token = _TokenState()
        if not access:
            return True
        try:
            self.session.post(
                self._url("/api/v3/general/disconnectApi"),
                headers={"Authorization": f"Bearer {access}"},
                timeout=self.timeout,
            )
        except Exception:
            pass
        return True

    def _ensure_token(self) -> str:
        with self._lock:
            now = time.time()
            if self._token.access_token and (
                self._token.expires_at == 0 or self._token.expires_at > now
            ):
                return self._token.access_token
        self.refresh()
        with self._lock:
            return self._token.access_token

    # ----- low-level request -----

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: Optional[Dict[str, Any]] = None,
        retry_on_401: bool = True,
    ) -> Any:
        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = self._url(path)
        try:
            resp = self.session.request(
                method.upper(),
                url,
                headers=headers,
                json=json_body,
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as ex:
            raise BulutklinikError(f"Istek hatasi: {ex}") from ex
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw_text": resp.text[:500]}
        if resp.status_code == 401 and retry_on_401:
            self.refresh()
            return self.request(
                method, path,
                json_body=json_body, params=params, retry_on_401=False,
            )
        if resp.status_code >= 400:
            err = self._envelope_error(payload) or f"HTTP {resp.status_code}"
            raise BulutklinikError(err, status_code=resp.status_code, payload=payload)
        return payload

    # ----- yuksek seviye yardimcilar -----

    def get_branches(self) -> Any:
        return self.request("GET", "/api/v3/outher/branches")

    def search_doctors(self, query: Dict[str, Any]) -> Any:
        return self.request("POST", "/api/v3/outher/search", json_body=query)

    def doctor_slots(self, query: Dict[str, Any]) -> Any:
        return self.request("POST", "/api/v3/outher/doctorSlots", json_body=query)

    def doctor_info(self, doctor_id: str) -> Any:
        return self.request("POST", f"/api/v3/outher/doctorInfos/{doctor_id}")

    def reservation(self, payload: Dict[str, Any]) -> Any:
        return self.request("POST", "/api/v3/outher/reservation", json_body=payload)

    def instant_reservation(self, payload: Dict[str, Any]) -> Any:
        return self.request("POST", "/api/v3/outher/instantReservation", json_body=payload)

    def appointment(self, payload: Dict[str, Any]) -> Any:
        return self.request("POST", "/api/v3/outher/appointment", json_body=payload)

    def appointments(self, payload: Optional[Dict[str, Any]] = None) -> Any:
        return self.request("POST", "/api/v3/outher/appointments", json_body=payload or {})

    def get_lab_test(self, barcode: str) -> Any:
        if not barcode:
            raise BulutklinikError("barcode gerekli")
        return self.request(
            "GET", f"/api/v3/outher/laboratoryTest/{barcode}")

    def save_lab_test(self, payload: Dict[str, Any]) -> Any:
        return self.request("PUT", "/api/v3/outher/laboratoryTest", json_body=payload)

    def push_device_data(self, payload: Dict[str, Any]) -> Any:
        return self.request("POST", "/api/v3/outher/device/patientData", json_body=payload)

    def register_device(self, payload: Dict[str, Any]) -> Any:
        return self.request("POST", "/api/v3/outher/device", json_body=payload)


def credentials_from_dict(data: Dict[str, Any]) -> BulutklinikCredentials:
    return BulutklinikCredentials(
        api_client_id=str(data.get("api_client_id") or "").strip(),
        api_secret_key=str(data.get("api_secret_key") or "").strip(),
        api_user_name=str(data.get("api_user_name") or "").strip(),
        api_user_password=str(data.get("api_user_password") or "").strip(),
        base_url=str(data.get("base_url") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
    )
