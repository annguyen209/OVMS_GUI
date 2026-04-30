from unittest.mock import patch, MagicMock
import httpx as _httpx
import pytest


def test_successful_search():
    from app.hf_search import search_hf_models
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"modelId": "OpenVINO/Qwen2.5-7B-int4-ov", "downloads": 5000},
        {"modelId": "OpenVINO/Llama-3-8B-int4-ov", "downloads": 3000},
    ]
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
        results, error = search_hf_models("qwen")
    assert error == ""
    assert len(results) == 2
    assert results[0]["model_id"] == "OpenVINO/Qwen2.5-7B-int4-ov"
    assert results[0]["downloads"] == 5000


def test_connection_error():
    from app.hf_search import search_hf_models
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = \
            _httpx.ConnectError("fail")
        results, error = search_hf_models("qwen")
    assert results == []
    assert "Could not reach" in error


def test_timeout_error():
    from app.hf_search import search_hf_models
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = \
            _httpx.TimeoutException("timeout")
        results, error = search_hf_models("qwen")
    assert results == []
    assert "timed out" in error


def test_non_200_response():
    from app.hf_search import search_hf_models
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
        results, error = search_hf_models("qwen")
    assert results == []
    assert "429" in error


def test_empty_query():
    from app.hf_search import search_hf_models
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
        results, error = search_hf_models("")
    assert error == ""
    assert results == []


def test_filter_options_structure():
    from app.hf_search import FILTER_OPTIONS
    assert "Text Generation" in FILTER_OPTIONS
    assert "Code Generation" in FILTER_OPTIONS
    assert "Reasoning" in FILTER_OPTIONS
    for label, (tag, extra) in FILTER_OPTIONS.items():
        assert isinstance(tag, str) and tag
        assert isinstance(extra, str)


def test_offset_and_limit_passed():
    from app.hf_search import search_hf_models
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    with patch("app.hf_search.httpx.Client") as mock_client:
        get_mock = mock_client.return_value.__enter__.return_value.get
        get_mock.return_value = mock_resp
        search_hf_models("test", offset=20, limit=10)
    call_kwargs = get_mock.call_args
    params = call_kwargs[1].get("params") or call_kwargs[0][1]
    assert params["offset"] == 20
    assert params["limit"] == 10
