"""Lokalny snapshot odpowiedzi Jira API. Brak sieci i narzędzi zapisu."""
try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server import MCPServer as FastMCP
from mcp.types import ToolAnnotations

from jira_read import OfflineReader, flatten_adf, format_comments, format_issue, format_page, format_pr, format_remote_links, pr_metadata

snapshot = OfflineReader()
TICKETS = snapshot.tickets
mcp = FastMCP('jira-jobs')
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)


def ticket_by_key(key: str) -> dict:
    return snapshot.get_issue(key)


@mcp.tool(annotations=READ_ONLY)
def search_tickets(query: str, status: str | None = None) -> str:
    """Szukaj wszystkich słów także w komentarzach, kluczach i hierarchii.

    Puste query zwraca wszystkie klucze. Status to dokładna nazwa, nie JQL.
    """
    return '\n'.join(f'{i["key"]} | {i["fields"]["status"]["name"]} | {i["fields"]["summary"]}' for i in snapshot.search_text(query, status)) or 'Brak zgłoszeń.'


@mcp.tool(annotations=READ_ONLY)
def get_ticket(key: str) -> str:
    """Pokaż opis, rodzica, bezpośrednie dzieci i powiązania, bez normalizacji."""
    return format_issue(snapshot.get_issue(key), snapshot.children(key))


@mcp.tool(annotations=READ_ONLY)
def list_comments(key: str) -> str:
    """Pełna treść komentarzy od najstarszego, z ID, datą i autorem technicznym."""
    return format_comments(snapshot.comments(key))


@mcp.tool(annotations=READ_ONLY)
def search_pages(query: str = '') -> str:
    """Szukaj wszystkich słów w tytule, HTML storage i adresach stron Confluence."""
    return '\n'.join(f'{p["id"]} | {p["title"]}' for p in snapshot.search_pages(query)) or 'Brak stron.'


@mcp.tool(annotations=READ_ONLY)
def get_page(page_id: str) -> str:
    """Treść strony Confluence z wersją, rodzicem i docelowymi URL odwołań."""
    return format_page(snapshot.get_page(page_id))


@mcp.tool(annotations=READ_ONLY)
def list_prs(query: str = '', source: str = 'github', repo: str | None = None) -> str:
    """Wszystkie stany PR; szukaj w tytułach, opisach, gałęziach, commitach i komentarzach."""
    return '\n'.join(f'{n} | {s} | {t} | {u}' for n, s, t, u in (pr_metadata(p, source) for p in snapshot.list_prs(query, source, repo))) or 'Brak PR.'


@mcp.tool(annotations=READ_ONLY)
def get_pr(number: int, source: str = 'github', repo: str | None = None) -> str:
    """Pełny PR wraz z gałęzią, SHA i wiadomościami commitów oraz ID komentarzy."""
    return format_pr(snapshot.get_pr(number, source, repo), source)


@mcp.tool(annotations=READ_ONLY)
def get_remote_links(key: str) -> str:
    """Istniejące linki zewnętrzne Jira; zachowuje także błędne powiązania."""
    return format_remote_links(snapshot.get_remote_links(key))


if __name__ == '__main__':
    mcp.run(transport='stdio')
