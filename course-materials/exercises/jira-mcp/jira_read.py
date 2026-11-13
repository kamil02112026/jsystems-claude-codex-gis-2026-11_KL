"""Read-only Jira Cloud CLI. Run with: uv run --with httpx jira_read.py --help."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from dataclasses import dataclass, field
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlsplit



@dataclass(frozen=True)
class Settings:
    base_url: str
    email: str = field(repr=False)
    token: str = field(repr=False)

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        required = ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
        missing = [name for name in required if not env.get(name, "").strip()]
        if missing:
            raise ValueError("Missing environment variables: " + ", ".join(missing))
        base = env["JIRA_BASE_URL"].rstrip("/")
        try:
            url = urlsplit(base)
            port = url.port
        except ValueError:
            raise ValueError("Invalid JIRA_BASE_URL") from None
        site = bool(re.fullmatch(r"[a-zA-Z0-9-]+\.atlassian\.net", url.hostname or ""))
        gateway = url.hostname == "api.atlassian.com" and bool(re.fullmatch(r"/ex/jira/[a-zA-Z0-9-]+", url.path))
        if url.scheme != "https" or url.username or url.password or url.query or url.fragment or port not in (None, 443) or not (gateway or (site and not url.path)):
            raise ValueError("Invalid JIRA_BASE_URL: use an HTTPS Atlassian site or scoped Jira gateway")
        cloud_id = env.get("JIRA_CLOUD_ID", "").strip()
        if cloud_id:
            if not re.fullmatch(r"[a-zA-Z0-9-]+", cloud_id):
                raise ValueError("Invalid JIRA_CLOUD_ID")
            base = f"https://api.atlassian.com/ex/jira/{cloud_id}"
        return cls(base, env["JIRA_EMAIL"], env["JIRA_API_TOKEN"])


def flatten_adf(node):
    """Keep paragraph boundaries, cards and link destinations without importing MCP."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    kind = node.get("type")
    if kind == "text":
        text = node.get("text", "")
        for mark in node.get("marks", []):
            href = mark.get("attrs", {}).get("href")
            if mark.get("type") == "link" and href and href != text:
                text += f" ({href})"
        return text
    if kind == "hardBreak":
        return "\n"
    if kind in {"inlineCard", "blockCard"}:
        return node.get("attrs", {}).get("url", "")
    text = "".join(flatten_adf(child) for child in node.get("content", []))
    return text.rstrip("\n") + "\n" if kind in {"paragraph", "heading", "listItem", "tableRow", "codeBlock", "blockquote"} else text


def issue_key(key):
    key = key.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*-[0-9]+", key):
        raise ValueError("Invalid issue key")
    return key


class JiraReader:
    def __init__(self, settings, *, transport=None):
        import httpx  # Optional for offline CLI/MCP; required only by live mode.
        self.http = httpx.Client(base_url=settings.base_url + "/", auth=httpx.BasicAuth(settings.email, settings.token), headers={"Accept": "application/json"}, timeout=30, follow_redirects=False, transport=transport)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def request(self, method, path, **kwargs):
        if method != "GET" or not re.fullmatch(r"/rest/api/3/(search/jql|issue/[A-Z][A-Z0-9_]*-[0-9]+(?:/comment)?)", path):
            raise ValueError("Read-only client refuses this method or endpoint")
        return self._send(method, path, **kwargs)

    def _send(self, method, path, **kwargs):
        import httpx
        try:
            response = self.http.request(method, path.lstrip("/"), **kwargs)
        except httpx.HTTPError:
            raise ValueError("Jira connection failed; check network and JIRA_BASE_URL") from None
        if not response.is_success:
            hint = " Check token scopes and product/project access." if response.status_code in (401, 403) else ""
            if response.status_code == 429:
                hint = " Rate limit reached; wait before a manual retry."
            raise ValueError(f"Jira HTTP {response.status_code}.{hint}")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            raise ValueError("Jira returned invalid JSON") from None

    def search(self, jql, fields="summary,status,labels"):
        params = {"jql": jql, "maxResults": 100, "fields": fields}
        result, seen = [], set()
        while True:
            page = self.request("GET", "/rest/api/3/search/jql", params=params)
            result.extend(page["issues"])
            token = page.get("nextPageToken")
            if page.get("isLast") is True or not token:
                return result
            if token in seen:
                raise ValueError("Jira pagination repeated nextPageToken")
            seen.add(token)
            params["nextPageToken"] = token

    def get_issue(self, key):
        return self.request("GET", f"/rest/api/3/issue/{issue_key(key)}", params={"fields": "summary,description,status,created,priority,duedate,labels,issuelinks,project,issuetype,parent,subtasks"})

    def comments(self, key):
        result, start = [], 0
        while True:
            page = self.request("GET", f"/rest/api/3/issue/{issue_key(key)}/comment", params={"startAt": start, "maxResults": 100, "orderBy": "created"})
            items = page["comments"]
            result.extend(items)
            start += len(items)
            if start >= page["total"]:
                return result
            if not items:
                raise ValueError("Jira comment pagination stopped before total")


def format_issue(issue, children=None):
    fields = issue["fields"]
    lines = [issue["key"], "Tytuł: " + fields.get("summary", ""), "Status: " + fields.get("status", {}).get("name", ""), "Utworzono: " + fields.get("created", ""), "Etykiety: " + ", ".join(fields.get("labels", [])), "Opis:", flatten_adf(fields.get("description")).strip(), "Powiązania:"]
    parent = (fields.get("parent") or {}).get("key", "Brak")
    lines[4:4] = ["Priorytet: " + (fields.get("priority") or {}).get("name", "Brak"), "Termin Jira (duedate): " + (fields.get("duedate") or "Brak")]
    children = fields.get("subtasks", []) if children is None else children
    lines[-1:-1] = ["Typ: " + fields.get("issuetype", {}).get("name", ""), "Rodzic: " + parent, "Dzieci: " + (", ".join(child["key"] for child in children) or "Brak")]
    for link in fields.get("issuelinks", []):
        direction = "outward" if "outwardIssue" in link else "inward"
        lines.append(f'{link["type"].get(direction, link["type"].get("name", ""))}: {link[direction + "Issue"]["key"]}')
    return "\n".join(lines)


def format_comments(comments):
    return "\n\n".join(f'{c["id"]} | {c["created"]} | {c.get("author", {}).get("displayName", "")}\n{flatten_adf(c["body"]).strip()}' for c in comments) or "Brak komentarzy."



DATA_PATH = Path(__file__).resolve().parents[2] / "exercise-data/jira-jobs/tickets.json"


class StorageText(HTMLParser):
    """Keep readable HTML boundaries and explicit reference destinations."""
    def __init__(self):
        super().__init__()
        self.parts = []
        self.href = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
        if tag in ("p", "div", "li", "tr", "br", "pre", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.parts.append(f" ({self.href})")
            self.href = None
        if tag in ("p", "div", "li", "tr", "pre", "h1", "h2", "h3"):
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_data(self, data):
        self.parts.append(data)


def format_page(page):
    parser = StorageText()
    parser.feed(page["body"]["storage"]["value"])
    return f'{page["id"]} | {page["title"]}\nRodzic: {page.get("parentId") or "Brak"}\nPrzestrzeń: {page["spaceId"]}\nWersja: {json.dumps(page["version"], ensure_ascii=False)}\nLinki: {json.dumps(page.get("_links", {}), ensure_ascii=False)}\n' + ''.join(parser.parts).strip()


def pr_metadata(bundle, source='github'):
    """A display view only; keep each provider's captured response unchanged."""
    if source == 'github':
        pr = bundle['pr']
        return pr['number'], pr['state'], pr['title'], pr['html_url']
    if source == 'bitbucket':
        pr = bundle['pr']['data']
        return pr['id'], pr['state'], pr['title'], pr['links']['html']['href']
    raise ValueError('Invalid PR source: use github or bitbucket')


def format_remote_links(links):
    return '\n'.join(json.dumps(link, ensure_ascii=False) for link in links) or 'Brak linków zewnętrznych.'


def format_pr(bundle, source='github'):
    if source == 'bitbucket':
        pr = bundle['pr']['data']
        number, state, title, url = pr_metadata(bundle, source)
        lines = [f'bitbucket PR #{number} | {title}', f'Stan: {state}', f'URL: {url}', f'Gałąź: {pr["source"]["branch"]["name"]}', f'Utworzono: {pr.get("created_on", "")}', 'Opis:', pr.get('summary', {}).get('raw', ''), 'Commity:']
        for commit in bundle['commits']['data']['values']:
            lines.append(f'{commit["hash"]} | {commit["message"]}')
        lines.append('Komentarze:')
        for comment in bundle['comments']['data']['values']:
            lines.append(f'comment:{comment["id"]} | {comment.get("created_on", "")} | {comment.get("user", {}).get("display_name", "")}\n{comment["content"].get("raw", "")}')
        lines.append('Linki Jira:')
        for key, links in bundle.get('jira_remote_links', {}).items():
            lines.append(key + '\n' + format_remote_links(links))
        lines.append('Diffy: brak osobnego zasobu diff w tym snapshocie; użyj dostępnej treści opisu i commitów.')
        return '\n'.join(lines)
    pr_metadata(bundle, source)  # Reject unknown providers before accessing data.
    # Commits and discussion comments are separate REST resources in the bundle.
    pr = bundle['pr']
    lines = [f'PR #{pr["number"]} | {pr["title"]}', f'Stan: {pr["state"]}', f'URL: {pr["html_url"]}', f'Gałąź: {pr["head"]["ref"]}', f'Utworzono: {pr.get("created_at", "")}', 'Opis:', pr.get('body') or '', 'Commity:']
    for commit in bundle.get('commits', []):
        lines.append(f'{commit["sha"]} | {commit["commit"]["message"]}')
    lines.append('Komentarze:')
    for kind in ('comments', 'review_comments'):
        for comment in bundle.get(kind, []):
            lines.append(f'{kind}:{comment["id"]} | {comment.get("created_at", "")} | {comment.get("user", {}).get("login", "")} | {comment.get("path", "")}\n{comment.get("body") or ""}')
    lines.append('Pliki i diffy:')
    for file in bundle.get('files', []):
        lines.append(f'{file["filename"]}\n{file.get("patch", "Brak patch w eksporcie")}')
    return '\n'.join(lines)


class OfflineReader:
    """Read a captured search response. A deliberately bounded JQL subset."""
    def __init__(self, path=DATA_PATH):
        self.data_dir = Path(path).parent
        self.tickets = json.loads(Path(path).read_text(encoding="utf-8"))["issues"]
        self.by_key = {issue["key"]: issue for issue in self.tickets}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get_issue(self, key):
        key = issue_key(key)
        if key not in self.by_key:
            raise ValueError(f"Nie znaleziono zgłoszenia: {key}")
        return deepcopy(self.by_key[key])

    def children(self, key):
        return [issue for issue in self.tickets if (issue["fields"].get("parent") or {}).get("key") == issue_key(key)]

    def comments(self, key):
        return sorted(self.get_issue(key)["fields"].get("comment", {}).get("comments", []), key=lambda c: (c["created"], c["id"]))

    def _references(self, filename, collection):
        path = self.data_dir / filename
        if not path.is_file():
            raise ValueError(f"Brak snapshotu {filename}; zgłoś prowadzącemu")
        return json.loads(path.read_text(encoding="utf-8"))[collection]

    def search_pages(self, query=""):
        return [p for p in self._references('confluence-pages.json', 'results') if all(word in format_page(p).casefold() for word in query.casefold().split())]

    def get_page(self, page_id):
        if not re.fullmatch(r'[0-9]+', str(page_id)):
            raise ValueError('Invalid page ID')
        for page in self.search_pages():
            if str(page['id']) == str(page_id):
                return page
        raise ValueError(f'Nie znaleziono strony: {page_id}')

    def list_prs(self, query="", source='github', repo=None):
        if source not in ('github', 'bitbucket'):
            raise ValueError('Invalid PR source: use github or bitbucket')
        bundles = self._references(source + '-prs.json', 'pull_requests')
        if source == 'bitbucket':
            bundles += self._references('bitbucket-prs.json', 'other_repo_pull_requests')
        return [bundle for bundle in bundles if (repo is None or pr_metadata(bundle, source)[3].split('/')[4] == repo) and all(word in format_pr(bundle, source).casefold() for word in query.casefold().split())]

    def get_pr(self, number, source='github', repo=None):
        if not re.fullmatch(r'[1-9][0-9]*', str(number)):
            raise ValueError('Invalid PR number')
        # Bitbucket numbers are repository-local. Default to the exercise repo.
        if source == 'bitbucket' and repo is None:
            repo = 'map-data-jobs-pipelines'
        for pr in self.list_prs(source=source, repo=repo):
            if pr_metadata(pr, source)[0] == int(number):
                return pr
        raise ValueError(f'Nie znaleziono PR: {number}')

    def get_remote_links(self, key):
        key = self.get_issue(key)['key']
        path = self.data_dir / 'remote-links.json'
        if not path.is_file():
            raise ValueError('Brak snapshotu remote-links.json; zgłoś prowadzącemu')
        return json.loads(path.read_text(encoding='utf-8')).get(key, [])

    def search_text(self, query, status=None):
        return [issue for issue in self.tickets if (not status or issue["fields"]["status"]["name"].casefold() == status.casefold()) and all(word in (format_issue(issue, self.children(issue["key"])) + " " + format_comments(self.comments(issue["key"]))).casefold() for word in query.casefold().split())]

    def search(self, jql, fields="summary,status,labels"):
        # Reject unsupported syntax rather than silently widening the selection.
        order = re.search(r"\s+ORDER\s+BY\s+key(?:\s+(ASC|DESC))?\s*$", jql, re.I)
        expression = jql[:order.start()].strip() if order else jql.strip()
        clauses = []
        value_pattern = r'(?P<value>"[^"\\]*"|\'[^\'\\]*\'|[A-Za-z0-9_.:-]+)'
        clause_pattern = re.compile(r"(?P<field>project|labels|status|issuetype|parent|key|text)\s*(?P<op>=|~)\s*" + value_pattern, re.I)
        while expression:
            match = clause_pattern.match(expression)
            if not match:
                raise ValueError("Offline JQL: supported fields project, labels, status, issuetype, parent, key (=), text (~), AND and ORDER BY key")
            field_name, operator, value = match["field"].lower(), match["op"], match["value"].strip("\'\"")
            if (field_name == "text") != (operator == "~"):
                raise ValueError("Offline JQL: text requires ~; other fields require =")
            clauses.append((field_name, value.casefold()))
            expression = expression[match.end():].strip()
            if expression:
                conjunction = re.match(r"AND\s+", expression, re.I)
                if not conjunction or not expression[conjunction.end():].strip():
                    raise ValueError("Offline JQL: only AND combinations are supported")
                expression = expression[conjunction.end():].strip()
        if not clauses:
            raise ValueError("Offline JQL: empty query; use project = TEST")
        result = self.tickets
        for name, value in clauses:
            def matches(issue):
                f = issue["fields"]
                if name == "text":
                    return value in (format_issue(issue, self.children(issue["key"])) + " " + format_comments(self.comments(issue["key"]))).casefold()
                actual = {"project": f.get("project", {}).get("key", ""), "status": f.get("status", {}).get("name", ""), "issuetype": f.get("issuetype", {}).get("name", ""), "parent": (f.get("parent") or {}).get("key", ""), "key": issue["key"], "labels": f.get("labels", [])}[name]
                return value in [label.casefold() for label in actual] if isinstance(actual, list) else actual.casefold() == value
            result = [issue for issue in result if matches(issue)]
        return sorted(result, key=lambda i: int(i["key"].rsplit("-", 1)[1]), reverse=bool(order and (order[1] or "").upper() == "DESC")) if order else result


def main(argv=None, *, env=None, transport=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Read the sanitized local snapshot, without credentials or network")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("search").add_argument("jql")
    for command in ("get", "comments"):
        sub.add_parser(command).add_argument("key")
    sub.add_parser('pages').add_argument('query', nargs='?', default='')
    sub.add_parser('page').add_argument('id')
    sub.add_parser('remotelinks').add_argument('key')
    for command, argument in (('prs', 'query'), ('pr', 'number')):
        command_parser = sub.add_parser(command)
        command_parser.add_argument(argument, **({'nargs': '?', 'default': ''} if command == 'prs' else {}))
        command_parser.add_argument('--source', choices=('github', 'bitbucket'), default='github')
        command_parser.add_argument('--repo', help='Repository name; Bitbucket PR numbers are repository-local')
    args = parser.parse_args(argv)
    try:
        environment = os.environ if env is None else env
        offline = args.offline or environment.get("JIRA_OFFLINE") == "1"
        if args.command in ('pages', 'page', 'prs', 'pr', 'remotelinks') and not offline:
            raise ValueError('Confluence, PR i linki zewnętrzne: te polecenia wymagają trybu --offline')
        api = OfflineReader() if offline else JiraReader(Settings.from_env(environment), transport=transport)
        with api:
            if args.command == "search":
                issues = api.search(args.jql)
                print("\n".join(f'{i["key"]} | {i["fields"].get("status", {}).get("name", "")} | {i["fields"]["summary"]}' for i in issues))
                print(f"Liczba zgłoszeń: {len(issues)}")
            elif args.command == "get":
                print(format_issue(api.get_issue(args.key), api.children(args.key) if offline else None))
            elif args.command == 'comments':
                print(format_comments(api.comments(args.key)))
            elif args.command == 'pages':
                pages = api.search_pages(args.query)
                print('\n'.join(f'{p["id"]} | {p["title"]}' for p in pages))
                print(f'Liczba stron: {len(pages)}')
            elif args.command == 'page':
                print(format_page(api.get_page(args.id)))
            elif args.command == 'prs':
                prs = api.list_prs(args.query, source=args.source, repo=args.repo)
                print('\n'.join(f'{n} | {s} | {t} | {u}' for n, s, t, u in (pr_metadata(p, args.source) for p in prs)))
                print(f'Liczba PR: {len(prs)}')
            elif args.command == 'pr':
                print(format_pr(api.get_pr(args.number, source=args.source, repo=args.repo), args.source))
            elif args.command == 'remotelinks':
                print(format_remote_links(api.get_remote_links(args.key)))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        # Do not echo response bodies, URLs, environment values or exception chains.
        print(str(error) if isinstance(error, ValueError) else "Unexpected Jira response shape", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
