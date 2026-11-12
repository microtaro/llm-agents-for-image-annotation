def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["app"] == "agent-app"


def test_a_web_page_cannot_reach_the_app(client):
    # 2026-11-06: /mcp had the SDK's check, /v1 had none: a false Host made and deleted a dataset,
    # and a plain POST from another site reached /v1/quit.
    assert client.get("/v1/datasets", headers={"Host": "a.example"}).status_code == 421
    assert (
        client.post("/v1/quit", headers={"Origin": "https://a.example"}).status_code
        == 403
    )
    assert (
        client.get("/v1/datasets", headers={"Host": "localhost:5110"}).status_code
        == 200
    )
    assert (
        client.get(
            "/v1/datasets", headers={"Origin": "http://localhost:5110"}
        ).status_code
        == 200
    )
