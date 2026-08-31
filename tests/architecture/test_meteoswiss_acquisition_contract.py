import hashlib
from datetime import datetime, timezone

import pytest
import requests

from decision.weather.meteoswiss_acquisition import (
    MeteoSwissAcquisitionError,
    MeteoSwissDownloadedAsset,
    MeteoSwissIntegrityError,
    decode_meteoswiss_csv,
    download_meteoswiss_observation_asset,
    fetch_meteoswiss_observation_asset,
)
from decision.weather.meteoswiss_assets import (
    METEOSWISS_OBSERVATION_COLLECTION,
    MeteoSwissAssetMetadataError,
    MeteoSwissGranularity,
    MeteoSwissObservationAsset,
    MeteoSwissProductFamily,
)


STAC_URL = (
    "https://data.geo.admin.ch/api/stac/v1/collections/"
    "ch.meteoschweiz.ogd-smn/items/abo"
)
ASSET_HREF = (
    "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/abo/"
    "ogd-smn_abo_t_recent.csv"
)
CONTENT = "station_abbr;station_name\nABO;Adelboden\n".encode("cp1252")
CHECKSUM = "1220" + hashlib.sha256(CONTENT).hexdigest()


def stac_item():
    return {
        "type": "Feature",
        "collection": METEOSWISS_OBSERVATION_COLLECTION,
        "id": "abo",
        "properties": {"title": "Adelboden (ABO)"},
        "assets": {
            "ogd-smn_abo_t_recent.csv": {
                "type": "text/csv",
                "href": ASSET_HREF,
                "updated": "2026-08-31T02:27:41.501431Z",
                "file:checksum": CHECKSUM,
            }
        },
    }


def observation_asset(**changes):
    values = {
        "station_id": "abo",
        "granularity": MeteoSwissGranularity.TEN_MINUTES,
        "product_family": MeteoSwissProductFamily.RECENT,
        "href": ASSET_HREF,
        "asset_key": "ogd-smn_abo_t_recent.csv",
        "checksum": CHECKSUM,
        "asset_updated_at_utc": datetime(
            2026, 8, 31, 2, 27, 41, 501431, tzinfo=timezone.utc
        ),
    }
    values.update(changes)
    return MeteoSwissObservationAsset(**values)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code=200,
        headers=None,
        content=b"response",
        json_payload=None,
        json_error=None,
        chunks=None,
        stream_error=None,
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content
        self._json_payload = json_payload
        self._json_error = json_error
        self._chunks = chunks if chunks is not None else (content,)
        self._stream_error = stream_error
        self.closed = False

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_payload

    def iter_content(self, *, chunk_size):
        assert chunk_size == 64 * 1024
        if self._stream_error is not None:
            raise self._stream_error
        yield from self._chunks

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def fetch_with(response, **changes):
    session = FakeSession(response)
    selected = fetch_meteoswiss_observation_asset(
        changes.pop("station_id", "abo"),
        granularity=changes.pop(
            "granularity", MeteoSwissGranularity.TEN_MINUTES
        ),
        product_family=changes.pop(
            "product_family", MeteoSwissProductFamily.RECENT
        ),
        session=session,
        **changes,
    )
    return selected, session


def stac_response(**changes):
    values = {
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "content": b"{stac-json}",
        "json_payload": stac_item(),
    }
    values.update(changes)
    return FakeResponse(**values)


def assert_error(error, *, code, retriable, status_code):
    assert error.value.code == code
    assert error.value.retriable is retriable
    assert error.value.status_code == status_code


def test_fetch_uses_exact_stac_url_timeout_and_redirect_policy():
    selected, session = fetch_with(stac_response())

    assert selected == observation_asset()
    assert session.calls == [
        (
            STAC_URL,
            {"timeout": (5.0, 30.0), "allow_redirects": False},
        )
    ]


@pytest.mark.parametrize("station_id", ("ABO", "ab", "ab1", "äbo", " abo"))
def test_invalid_station_is_rejected_before_network(station_id):
    session = FakeSession(stac_response())

    with pytest.raises(MeteoSwissAcquisitionError) as error:
        fetch_meteoswiss_observation_asset(
            station_id,
            granularity=MeteoSwissGranularity.TEN_MINUTES,
            product_family=MeteoSwissProductFamily.RECENT,
            session=session,
        )

    assert_error(
        error, code="invalid_station_id", retriable=False, status_code=None
    )
    assert session.calls == []


@pytest.mark.parametrize(
    "media_type",
    ("application/json", "application/geo+json; charset=utf-8"),
)
def test_fetch_accepts_stac_json_content_types(media_type):
    selected, _ = fetch_with(
        stac_response(headers={"Content-Type": media_type})
    )

    assert selected.station_id == "abo"


@pytest.mark.parametrize(
    "response",
    (
        stac_response(content=b""),
        stac_response(json_error=ValueError("invalid json")),
    ),
)
def test_fetch_rejects_empty_or_invalid_json(response):
    with pytest.raises(MeteoSwissAcquisitionError) as error:
        fetch_with(response)

    assert_error(
        error, code="invalid_stac_json", retriable=False, status_code=None
    )


def test_valid_json_with_invalid_stac_shape_uses_selector_error():
    with pytest.raises(MeteoSwissAssetMetadataError):
        fetch_with(stac_response(json_payload={"not": "a STAC item"}))


@pytest.mark.parametrize(
    ("status", "code", "retriable"),
    (
        (301, "redirect_not_allowed", False),
        (404, "item_not_found", False),
        (429, "rate_limited", True),
        (503, "server_error", True),
        (403, "http_error", False),
        (204, "unexpected_http_status", False),
    ),
)
def test_fetch_rejects_non_200_statuses(status, code, retriable):
    with pytest.raises(MeteoSwissAcquisitionError) as error:
        fetch_with(stac_response(status_code=status))

    assert_error(error, code=code, retriable=retriable, status_code=status)


@pytest.mark.parametrize(
    ("transport_error", "code"),
    (
        (requests.Timeout("slow"), "timeout"),
        (requests.ConnectionError("offline"), "transport_error"),
    ),
)
def test_fetch_wraps_transport_errors(transport_error, code):
    with pytest.raises(MeteoSwissAcquisitionError) as error:
        fetch_with(transport_error)

    assert_error(error, code=code, retriable=True, status_code=None)


def download_with(response, *, asset=None, **changes):
    session = FakeSession(response)
    downloaded = download_meteoswiss_observation_asset(
        observation_asset() if asset is None else asset,
        session=session,
        **changes,
    )
    return downloaded, session


def asset_response(**changes):
    values = {
        "headers": {
            "Content-Type": "text/csv; charset=windows-1252",
            "Content-Length": str(len(CONTENT)),
        },
        "content": CONTENT,
        "chunks": (CONTENT[:10], CONTENT[10:]),
    }
    values.update(changes)
    return FakeResponse(**values)


def test_download_uses_exact_href_transport_contract_and_preserves_provenance():
    asset = observation_asset()
    downloaded, session = download_with(asset_response(), asset=asset)

    assert downloaded == MeteoSwissDownloadedAsset(asset=asset, content=CONTENT)
    assert downloaded.asset is asset
    assert session.calls == [
        (
            ASSET_HREF,
            {
                "headers": {"Accept-Encoding": "identity"},
                "stream": True,
                "timeout": (5.0, 30.0),
                "allow_redirects": False,
            },
        )
    ]


@pytest.mark.parametrize(
    "href",
    (
        "http://data.geo.admin.ch/file.csv",
        "https://example.test/file.csv",
        "https://user@data.geo.admin.ch/file.csv",
        "https://data.geo.admin.ch:444/file.csv",
    ),
)
def test_download_rejects_untrusted_url_before_network(href):
    session = FakeSession(asset_response())

    with pytest.raises(MeteoSwissAcquisitionError) as error:
        download_meteoswiss_observation_asset(
            observation_asset(href=href), session=session
        )

    assert_error(
        error, code="untrusted_asset_url", retriable=False, status_code=None
    )
    assert session.calls == []


@pytest.mark.parametrize(
    "media_type",
    ("text/csv", "text/plain", "application/octet-stream", None),
)
def test_download_accepts_compatible_or_absent_content_type(media_type):
    headers = {"Content-Length": str(len(CONTENT))}
    if media_type is not None:
        headers["Content-Type"] = media_type

    downloaded, _ = download_with(asset_response(headers=headers))

    assert downloaded.content == CONTENT


def test_download_rejects_incompatible_content_type():
    with pytest.raises(MeteoSwissAcquisitionError) as error:
        download_with(asset_response(headers={"Content-Type": "text/html"}))

    assert_error(
        error,
        code="unexpected_asset_content_type",
        retriable=False,
        status_code=200,
    )


@pytest.mark.parametrize(
    ("status", "code", "retriable"),
    (
        (302, "redirect_not_allowed", False),
        (404, "asset_not_found", False),
        (429, "rate_limited", True),
        (500, "server_error", True),
        (401, "http_error", False),
        (206, "unexpected_http_status", False),
    ),
)
def test_download_rejects_non_200_statuses(status, code, retriable):
    with pytest.raises(MeteoSwissAcquisitionError) as error:
        download_with(asset_response(status_code=status))

    assert_error(error, code=code, retriable=retriable, status_code=status)


def test_download_rejects_declared_or_streamed_oversize():
    with pytest.raises(MeteoSwissAcquisitionError) as declared_error:
        download_with(
            asset_response(headers={"Content-Length": "100"}), max_bytes=99
        )
    assert_error(
        declared_error,
        code="asset_too_large",
        retriable=False,
        status_code=200,
    )

    with pytest.raises(MeteoSwissAcquisitionError) as streamed_error:
        download_with(
            asset_response(
                headers={"Content-Length": "malformed"},
                chunks=(b"123", b"456"),
            ),
            max_bytes=5,
        )
    assert_error(
        streamed_error,
        code="asset_too_large",
        retriable=False,
        status_code=200,
    )


def test_download_rejects_invalid_max_bytes_before_network():
    session = FakeSession(asset_response())

    with pytest.raises(MeteoSwissAcquisitionError) as error:
        download_meteoswiss_observation_asset(
            observation_asset(), session=session, max_bytes=0
        )

    assert_error(error, code="invalid_max_bytes", retriable=False, status_code=None)
    assert session.calls == []


@pytest.mark.parametrize(
    ("transport_error", "code"),
    (
        (requests.Timeout("slow"), "timeout"),
        (requests.ConnectionError("offline"), "transport_error"),
    ),
)
def test_download_wraps_get_and_stream_transport_errors(transport_error, code):
    with pytest.raises(MeteoSwissAcquisitionError) as get_error:
        download_with(transport_error)
    assert_error(get_error, code=code, retriable=True, status_code=None)

    with pytest.raises(MeteoSwissAcquisitionError) as stream_error:
        download_with(asset_response(stream_error=transport_error))
    assert_error(stream_error, code=code, retriable=True, status_code=None)


def test_valid_sha2_256_multihash_is_deterministic():
    first, _ = download_with(asset_response())
    second, _ = download_with(asset_response())

    assert first == second


def test_checksum_mismatch_is_rejected_fail_closed():
    wrong_checksum = "1220" + ("0" * 64)

    with pytest.raises(MeteoSwissIntegrityError) as error:
        download_with(asset_response(), asset=observation_asset(checksum=wrong_checksum))

    assert_error(
        error, code="checksum_mismatch", retriable=False, status_code=None
    )


def test_unsupported_and_malformed_checksums_are_distinguished():
    unsupported = "1320" + hashlib.sha256(CONTENT).hexdigest()
    with pytest.raises(MeteoSwissIntegrityError) as unsupported_error:
        download_with(asset_response(), asset=observation_asset(checksum=unsupported))
    assert_error(
        unsupported_error,
        code="unsupported_checksum",
        retriable=False,
        status_code=None,
    )

    with pytest.raises(MeteoSwissIntegrityError) as malformed_error:
        download_with(asset_response(), asset=observation_asset(checksum="1220XYZ"))
    assert_error(
        malformed_error,
        code="invalid_checksum",
        retriable=False,
        status_code=None,
    )


def test_decode_cp1252_is_exact_and_deterministic():
    content = b"Adelboden;Temp\xe9rature"

    assert decode_meteoswiss_csv(content) == "Adelboden;Température"
    assert decode_meteoswiss_csv(content) == decode_meteoswiss_csv(content)


def test_decode_rejects_undefined_cp1252_byte_without_fallback():
    with pytest.raises(MeteoSwissAcquisitionError) as error:
        decode_meteoswiss_csv(b"invalid:\x81")

    assert_error(
        error, code="invalid_csv_encoding", retriable=False, status_code=None
    )
