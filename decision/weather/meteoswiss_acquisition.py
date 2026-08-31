from __future__ import annotations

import hashlib
import hmac
import string
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from decision.weather.meteoswiss_assets import (
    METEOSWISS_OBSERVATION_COLLECTION,
    MeteoSwissGranularity,
    MeteoSwissObservationAsset,
    MeteoSwissProductFamily,
    select_meteoswiss_observation_asset,
)


_STAC_ITEM_BASE_URL = (
    "https://data.geo.admin.ch/api/stac/v1/collections/"
    f"{METEOSWISS_OBSERVATION_COLLECTION}/items"
)
_DEFAULT_TIMEOUT = (5.0, 30.0)
_STAC_CONTENT_TYPES = frozenset(("application/json", "application/geo+json"))
_ASSET_CONTENT_TYPES = frozenset(
    ("text/csv", "text/plain", "application/octet-stream")
)
_DOWNLOAD_CHUNK_SIZE = 64 * 1024
_SHA2_256_MULTIHASH_PREFIX = "1220"
_SHA2_256_MULTIHASH_LENGTH = 68
_LOWERCASE_HEX = frozenset(string.digits + "abcdef")


class MeteoSwissAcquisitionError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        retriable: bool,
        status_code: int | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.retriable = retriable
        self.status_code = status_code


class MeteoSwissIntegrityError(MeteoSwissAcquisitionError):
    pass


@dataclass(frozen=True)
class MeteoSwissDownloadedAsset:
    asset: MeteoSwissObservationAsset
    content: bytes


def _acquisition_error(
    code: str,
    *,
    retriable: bool,
    status_code: int | None = None,
) -> MeteoSwissAcquisitionError:
    return MeteoSwissAcquisitionError(
        code=code,
        retriable=retriable,
        status_code=status_code,
    )


def _validate_http_status(status_code: int, *, not_found_code: str) -> None:
    if status_code == 200:
        return
    if 300 <= status_code <= 399:
        code, retriable = "redirect_not_allowed", False
    elif status_code == 404:
        code, retriable = not_found_code, False
    elif status_code == 429:
        code, retriable = "rate_limited", True
    elif 500 <= status_code <= 599:
        code, retriable = "server_error", True
    elif 400 <= status_code <= 499:
        code, retriable = "http_error", False
    else:
        code, retriable = "unexpected_http_status", False
    raise _acquisition_error(
        code,
        retriable=retriable,
        status_code=status_code,
    )


def _content_type(headers: Mapping[str, str]) -> str | None:
    value = headers.get("Content-Type")
    if value is None:
        return None
    return value.partition(";")[0].strip().lower()


def _validate_station_id(station_id: object) -> str:
    if (
        not isinstance(station_id, str)
        or len(station_id) != 3
        or not station_id.isascii()
        or not station_id.isalpha()
        or not station_id.islower()
    ):
        raise _acquisition_error("invalid_station_id", retriable=False)
    return station_id


def fetch_meteoswiss_observation_asset(
    station_id: str,
    *,
    granularity: MeteoSwissGranularity,
    product_family: MeteoSwissProductFamily,
    session: requests.Session,
    timeout: tuple[float, float] = _DEFAULT_TIMEOUT,
) -> MeteoSwissObservationAsset:
    station = _validate_station_id(station_id)
    url = f"{_STAC_ITEM_BASE_URL}/{station}"
    try:
        response = session.get(url, timeout=timeout, allow_redirects=False)
    except requests.Timeout as error:
        raise _acquisition_error("timeout", retriable=True) from error
    except requests.RequestException as error:
        raise _acquisition_error("transport_error", retriable=True) from error

    _validate_http_status(response.status_code, not_found_code="item_not_found")
    if _content_type(response.headers) not in _STAC_CONTENT_TYPES:
        raise _acquisition_error("unexpected_stac_content_type", retriable=False)
    if not response.content:
        raise _acquisition_error("invalid_stac_json", retriable=False)
    try:
        payload = response.json()
    except (TypeError, ValueError) as error:
        raise _acquisition_error("invalid_stac_json", retriable=False) from error

    return select_meteoswiss_observation_asset(
        payload,
        granularity=granularity,
        product_family=product_family,
    )


def _validate_asset_url(href: object) -> None:
    if not isinstance(href, str):
        raise _acquisition_error("untrusted_asset_url", retriable=False)
    try:
        parsed = urlparse(href)
        port = parsed.port
    except ValueError as error:
        raise _acquisition_error("untrusted_asset_url", retriable=False) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != "data.geo.admin.ch"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise _acquisition_error("untrusted_asset_url", retriable=False)


def _validate_checksum(content: bytes, checksum: object) -> None:
    if (
        not isinstance(checksum, str)
        or len(checksum) != _SHA2_256_MULTIHASH_LENGTH
        or any(character not in _LOWERCASE_HEX for character in checksum)
    ):
        raise MeteoSwissIntegrityError(
            code="invalid_checksum",
            retriable=False,
        )
    if not checksum.startswith(_SHA2_256_MULTIHASH_PREFIX):
        raise MeteoSwissIntegrityError(
            code="unsupported_checksum",
            retriable=False,
        )
    expected_digest = checksum[len(_SHA2_256_MULTIHASH_PREFIX) :]
    actual_digest = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise MeteoSwissIntegrityError(
            code="checksum_mismatch",
            retriable=False,
        )


def download_meteoswiss_observation_asset(
    asset: MeteoSwissObservationAsset,
    *,
    session: requests.Session,
    timeout: tuple[float, float] = _DEFAULT_TIMEOUT,
    max_bytes: int = 10_000_000,
) -> MeteoSwissDownloadedAsset:
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise _acquisition_error("invalid_max_bytes", retriable=False)
    _validate_asset_url(asset.href)
    try:
        response = session.get(
            asset.href,
            headers={"Accept-Encoding": "identity"},
            stream=True,
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.Timeout as error:
        raise _acquisition_error("timeout", retriable=True) from error
    except requests.RequestException as error:
        raise _acquisition_error("transport_error", retriable=True) from error

    try:
        _validate_http_status(response.status_code, not_found_code="asset_not_found")
        media_type = _content_type(response.headers)
        if media_type is not None and media_type not in _ASSET_CONTENT_TYPES:
            raise _acquisition_error(
                "unexpected_asset_content_type",
                retriable=False,
                status_code=response.status_code,
            )

        content_length = response.headers.get("Content-Length")
        try:
            declared_length = int(content_length) if content_length is not None else None
        except (TypeError, ValueError):
            declared_length = None
        if declared_length is not None and declared_length > max_bytes:
            raise _acquisition_error(
                "asset_too_large",
                retriable=False,
                status_code=response.status_code,
            )

        chunks = []
        total_bytes = 0
        try:
            for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise _acquisition_error(
                        "asset_too_large",
                        retriable=False,
                        status_code=response.status_code,
                    )
                chunks.append(chunk)
        except requests.Timeout as error:
            raise _acquisition_error("timeout", retriable=True) from error
        except requests.RequestException as error:
            raise _acquisition_error("transport_error", retriable=True) from error
        content = b"".join(chunks)
    finally:
        response.close()

    _validate_checksum(content, asset.checksum)
    return MeteoSwissDownloadedAsset(asset=asset, content=content)


def decode_meteoswiss_csv(content: bytes) -> str:
    try:
        return content.decode("cp1252", errors="strict")
    except UnicodeDecodeError as error:
        raise _acquisition_error("invalid_csv_encoding", retriable=False) from error
