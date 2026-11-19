"""Dependency-light contract checks for the Docker/MCP-only UI implementation."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_ui_is_mcp_only_for_financial_data():
    text = (ROOT / 'src/real_basket/ui/app.py').read_text(encoding='utf-8')
    for forbidden in ('load_basket', 'essential_index(', 'compare_with_cpi(',
                      'from real_basket.agents.tools', 'KnowledgeBase(', 'generate_all('):
        assert forbidden not in text
    assert 'call_tool("get_dashboard_snapshot")' in text
    assert 'agent_service.client import call_tool, url, ask' in text


def test_mcp_exposes_dashboard_pdf_storage_tools():
    text = (ROOT / 'src/real_basket/mcp_server/server.py').read_text(encoding='utf-8')
    node = ast.parse(text)
    names = {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name in ('get_dashboard_snapshot', 'generate_reports', 'get_reference_pdf',
                 'get_observations', 'get_prices', 'calculate_index', 'search_documents'):
        assert name in names


def test_compose_defines_four_services_and_persistence():
    text = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
    for value in ('realbasket-ui:', 'realbasket-agent:', 'realbasket-mcp:', 'weaviate:',
                  'realbasket_data:', 'weaviate_data:',
                  'http://realbasket-mcp:8001/mcp'):
        assert value in text
