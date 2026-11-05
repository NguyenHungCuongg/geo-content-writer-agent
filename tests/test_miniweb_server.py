from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from evals.miniweb.server import app

client = TestClient(app)


def test_server_never_serves_answer_key():
    """GET /evals/miniweb/answer_key.yaml và GET /..%2Fanswer_key.yaml -> 404."""
    resp1 = client.get("/evals/miniweb/answer_key.yaml")
    assert resp1.status_code == 404

    resp2 = client.get("/..%2Fanswer_key.yaml")
    assert resp2.status_code == 404

    resp3 = client.get("/answer_key.yaml")
    assert resp3.status_code == 404


def test_server_serves_manifest_page():
    """GET /{host}/{path} trả đúng trang có trong manifest (kể cả path tiếng Việt có dấu)."""
    resp = client.get("/vi.wikipedia.org/wiki/Đảo_nhiệt_đô_thị")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Đảo nhiệt đô thị" in resp.text


def test_server_handles_redirect():
    """GET /{host}/{path} với trang có redirect_to trả 302 với Location chính xác."""
    resp = client.get("/blogmaiton.example/uu-dai-son-chong-nong", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("location") == "https://khuyen-mai-x.example/"


@patch("asyncio.sleep", new_callable=AsyncMock)
def test_server_handles_delay(mock_sleep):
    """GET /{host}/{path} với delay_s gọi asyncio.sleep trước khi trả."""
    resp = client.get("/diendanxaydung.example/hoi-dap-mai-ton-nong")
    assert resp.status_code == 200
    mock_sleep.assert_awaited_once_with(20)


def test_server_search():
    """GET /search?q=&n=5 khớp từ khoá trên title + text, tách từ và xếp theo số từ trùng."""
    resp1 = client.get("/search?q=mái tôn&n=5")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "results" in data1
    assert len(data1["results"]) == 5

    # Tìm kiếm nhiều từ (q=sơn phản xạ mái tôn) vẫn trả kết quả thay vì 0 kết quả
    resp2 = client.get("/search?q=sơn phản xạ mái tôn&n=5")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert "results" in data2
    results2 = data2["results"]
    assert len(results2) == 5
    for item in results2:
        assert item["url"]
        assert item["title"]
        assert len(item["snippet"]) > 0


def test_server_search_empty_query():
    """GET /search với truy vấn rỗng trả về mảng kết quả rỗng."""
    resp = client.get("/search?q=&n=5")
    assert resp.status_code == 200
    assert resp.json() == {"results": []}


def test_server_unknown_path_returns_404():
    """Trang không có trong manifest trả về 404."""
    resp = client.get("/nonexistent.example/some/path")
    assert resp.status_code == 404
