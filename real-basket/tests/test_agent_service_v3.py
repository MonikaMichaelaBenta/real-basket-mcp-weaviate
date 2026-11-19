"""v3 architecture and API tests; do not require a running MCP server or LLM."""
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from real_basket.agent_service import api

ROOT = Path(__file__).resolve().parents[1]


def test_compose_has_four_services_and_separate_agent():
    services = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())['services']
    assert set(services) == {'realbasket-ui', 'realbasket-agent', 'realbasket-mcp', 'weaviate'}
    assert services['realbasket-agent']['environment']['REALBASKET_MCP_URL'] == 'http://realbasket-mcp:8001/mcp'
    assert services['realbasket-ui']['environment']['REALBASKET_AGENT_URL'] == 'http://realbasket-agent:8002'
    assert 'REALBASKET_MCP_URL' not in services['realbasket-ui']['environment']
    assert services['realbasket-ui']['depends_on']['realbasket-agent']['condition'] == 'service_healthy'
    assert 'ports' not in services['realbasket-agent']


def test_ui_uses_only_agent_http_client():
    source = (ROOT / 'src/real_basket/ui/app.py').read_text()
    assert 'from real_basket.agent_service.client import call_tool, url, ask' in source
    assert 'mcp_server.agent import ask' not in source
    assert 'mcp_server.client import call_tool' not in source


def test_api_health_and_tool_allowlist(monkeypatch):
    import sys
    from types import ModuleType
    stub = ModuleType('real_basket.mcp_server.client')
    stub.call_tool = lambda name, **kw: {'name': name, 'args': kw}
    monkeypatch.setitem(sys.modules, 'real_basket.mcp_server.client', stub)
    with TestClient(api.app) as c:
        assert c.get('/health').json()['status'] == 'ok'
        res = c.post('/tools/get_dashboard_snapshot', json={'arguments': {}})
        assert res.status_code == 200
        assert res.json()['result']['name'] == 'get_dashboard_snapshot'
        assert c.post('/tools/ingest_reference_pdfs', json={'arguments': {}}).status_code == 404


def test_api_chat_delegates_to_agent(monkeypatch):
    # Avoid importing Strands/LLM by patching the lazily loaded module below.
    import sys
    from types import ModuleType
    stub = ModuleType('real_basket.mcp_server.agent')
    stub.ask = lambda question, history: ('Antwort ' + question, ['calculate_index'])
    monkeypatch.setitem(sys.modules, 'real_basket.mcp_server.agent', stub)
    with TestClient(api.app) as c:
        r = c.post('/chat', json={'question': 'Test', 'history': []})
        assert r.status_code == 200
        assert r.json() == {'answer': 'Antwort Test', 'tools': ['calculate_index']}
