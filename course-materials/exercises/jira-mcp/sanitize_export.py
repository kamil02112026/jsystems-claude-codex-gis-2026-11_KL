"""Trainer-only: sanitize a captured Jira search export, preserving its fields.

Raw inputs stay outside the repository. No network or credential access.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote

UUID = r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'
FAKE_CLOUD = '00000000-0000-0000-0000-000000000000'
AVATAR = 'https://example.invalid/avatar.png'


def inline(text):
    """Convert the inline subset used in the seeded descriptions, recursively."""
    nodes, pos = [], 0
    pattern = r'(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|(?<!\w)_[^_\s](?:[^_]*?[^_\s])?_(?!\w)|\[[^\]]+\]\([^ )]+\))'
    for match in re.finditer(pattern, text):
        if match.start() > pos:
            nodes.append({'type': 'text', 'text': text[pos:match.start()]})
        token = match.group()
        if token.startswith('`'):
            children, mark = [{'type': 'text', 'text': token[1:-1]}], {'type': 'code'}
        elif token.startswith('['):
            label, href = token[1:].split('](', 1)
            children, mark = inline(label), {'type': 'link', 'attrs': {'href': href[:-1]}}
        else:
            width = 2 if token[:2] in ('**', '__') else 1
            children, mark = inline(token[width:-width]), {'type': 'strong' if width == 2 else 'em'}
        for child in children:
            child.setdefault('marks', []).append(mark)
        nodes.extend(children)
        pos = match.end()
    if pos < len(text):
        nodes.append({'type': 'text', 'text': text[pos:]})
    return nodes


def paragraph(text):
    content = []
    for index, line in enumerate(text.split('\n')):
        if index:
            content.append({'type': 'hardBreak'})
        content.extend(inline(line.rstrip()))
    return {'type': 'paragraph', 'content': content}


def markdown_to_adf(markdown):
    # The connector serialized literal backslash-n sequences into descriptions.
    markdown = markdown.replace(r'\n', '\n') if '\n' not in markdown else markdown
    lines, blocks, index = markdown.splitlines(), [], 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.lstrip().startswith('```'):
            language, code = line.strip()[3:].strip(), []
            index += 1
            while index < len(lines) and not lines[index].lstrip().startswith('```'):
                code.append(lines[index]); index += 1
            block = {'type': 'codeBlock'}
            if language:
                block['attrs'] = {'language': language}
            if code:
                block['content'] = [{'type': 'text', 'text': '\n'.join(code)}]
            blocks.append(block); index += 1
            continue
        heading = re.match(r'^(#{1,6})\s+(.*)$', line)
        if heading:
            blocks.append({'type': 'heading', 'attrs': {'level': len(heading[1])}, 'content': inline(heading[2])})
            index += 1; continue
        if line.strip().startswith('|') and index + 1 < len(lines) and re.fullmatch(r'[| :\-]+', lines[index + 1].strip()):
            rows = []
            header = True
            while index < len(lines) and lines[index].strip().startswith('|'):
                row = lines[index].strip()
                index += 1
                if re.fullmatch(r'[| :\-]+', row):
                    continue
                cells = [{'type': 'tableHeader' if header else 'tableCell', 'content': [paragraph(cell.strip())]} for cell in row.strip('|').split('|')]
                rows.append({'type': 'tableRow', 'content': cells}); header = False
            blocks.append({'type': 'table', 'content': rows}); continue
        item = re.match(r'^\s*(?:([-+*])|(\d+)[.)])\s+(.*)$', line)
        if item:
            ordered, items = bool(item[2]), []
            start = int(item[2]) if ordered else 1
            while index < len(lines):
                item = re.match(r'^\s*(?:([-+*])|(\d+)[.)])\s+(.*)$', lines[index])
                if not item or bool(item[2]) != ordered:
                    break
                items.append({'type': 'listItem', 'content': [paragraph(item[3])]}); index += 1
            block = {'type': 'orderedList' if ordered else 'bulletList', 'content': items}
            if ordered:
                block['attrs'] = {'order': start}
            blocks.append(block); continue
        para = [line]; index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r'^\s*(?:```|#{1,6}\s|\||[-+*]\s|\d+[.)]\s)', lines[index]):
            para.append(lines[index]); index += 1
        blocks.append(paragraph('\n'.join(para)))
    return {'type': 'doc', 'version': 1, 'content': blocks or [paragraph('')]}


def sanitize(raw):
    """Two passes remove identities also when repeated in URLs or free text."""
    replacements, accounts, bitbucket_users = {'devpowers': 'course-workspace'}, {}, {}

    def collect(node, context=''):
        if isinstance(node, dict):
            if node.get('display_name') or node.get('account_id') or ((node.get('type') == 'user' or context in ('author', 'user', 'reviewer', 'committer')) and (node.get('uuid') or node.get('nickname'))):
                identities = [node[k] for k in ('account_id', 'uuid', 'display_name', 'nickname') if node.get(k)]
                alias = next((bitbucket_users[v] for v in identities if v in bitbucket_users), None)
                if alias is None:
                    existing = next((re.search(r'course-(?:account|user)-(\d+)', v) for v in identities if re.search(r'course-(?:account|user)-(\d+)', v)), None)
                    alias = existing[1] if existing else str(len(set(bitbucket_users.values())) + 1)
                for value in identities:
                    bitbucket_users[value] = alias
                for key, prefix in (('account_id', 'course-account-'), ('uuid', '{course-user-'), ('display_name', 'Autor kursowy '), ('nickname', 'course-user-')):
                    if node.get(key):
                        replacements[node[key]] = prefix + alias + ('}' if key == 'uuid' else '')
            if context == 'author' and node.get('raw'):
                name = node['raw'].split('<', 1)[0].strip()
                if name:
                    replacements.setdefault(name, 'Autor (kurs)')
            account = node.get('accountId')
            if account:
                accounts.setdefault(account, f'712020:course-user-{len(accounts) + 1}')
                replacements[account] = account if re.fullmatch(r'712020:course-user-\d+', account) else accounts[account]
                for key in ('displayName', 'name', 'key'):
                    if isinstance(node.get(key), str) and node[key]:
                        replacements[node[key]] = 'Analityk (kurs)'
            if context == 'project' and node.get('name'):
                replacements[node['name']] = 'Projekt kursowy'
            if context in ('author', 'committer') and node.get('email') and node.get('name'):
                replacements[node['name']] = 'Autor (kurs)'
            if node.get('login'):
                login = node['login']
                alias = 'course-org' if login.casefold() in ('lucasmatuszewski', 'course-org') else 'course-user'
                replacements[login] = alias
                if node.get('name'):
                    replacements[node['name']] = 'Autor (kurs)'
            for key, value in node.items():
                if key.lower() in ('cloudid', 'cloud_id') and isinstance(value, str):
                    replacements[value] = FAKE_CLOUD
                collect(value, key)
        elif isinstance(node, list):
            for value in node:
                collect(value, context)
        elif isinstance(node, str):
            for cloud in re.findall(r'(?:/ex/(?:jira|confluence)/|ari:cloud:(?:jira|confluence):)(%s)' % UUID, node):
                replacements[cloud] = FAKE_CLOUD
            for email in re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', node):
                replacements[email] = '[email usunięty]'
    collect(raw)
    for old, new in list(replacements.items()):
        if quote(old, safe='') != old:
            replacements[quote(old, safe='')] = quote(new, safe='')
    pattern = re.compile('|'.join(re.escape(key) for key in sorted(replacements, key=len, reverse=True))) if replacements else None

    def scrub(text):
        # Space keys use a different alias from the same person's accountId.
        text = re.sub(r'(?:\\?~|%7e)557058(?::|%3a)?[a-z0-9%:_-]*', '~course-user', text, flags=re.I)
        if pattern:
            text = pattern.sub(lambda m: replacements[m.group()], text)
        text = re.sub(r'edukey\.atlassian\.net', 'course-site.atlassian.net', text, flags=re.I)
        text = re.sub(r'LucasMatuszewski', 'course-org', text, flags=re.I)
        return re.sub('edukey', 'Course', text, flags=re.I)

    def visit(node, context='', in_comment=False):
        if isinstance(node, dict):
            result = {}
            for key, value in node.items():
                if key in ('emailAddress', 'email'):
                    continue
                if key == 'avatarUrls' and isinstance(value, dict):
                    result[key] = {size: AVATAR for size in value}
                elif key == 'body' and in_comment and isinstance(value, str):
                    result[key] = markdown_to_adf(scrub(value).replace(r'\[', '[').replace(r'\]', ']'))
                elif key in ('avatarUrl', 'avatar_url'):
                    result[key] = AVATAR
                elif key == 'avatar' and isinstance(value, dict):
                    result[key] = {'href': AVATAR}
                elif key == 'displayName':
                    result[key] = 'Analityk (kurs)'
                elif key == 'description' and isinstance(value, str):
                    result[key] = markdown_to_adf(scrub(value)) if context == 'fields' else scrub(value)
                else:
                    result[key] = visit(value, key, in_comment or key == 'comment')
            if node.get('login'):
                # GitHub user IDs identify accounts; PR/comment IDs are evidence.
                alias = result['login']
                if 'id' in node:
                    result['id'] = 1001 if alias == 'course-org' else 2001
                if 'node_id' in node:
                    result['node_id'] = 'course-account-' + alias
            return result
        if isinstance(node, list):
            return [visit(item, context, in_comment) for item in node]
        if isinstance(node, str):
            text = scrub(node)
            return text.replace(r'\[', '[').replace(r'\]', ']') if in_comment else text
        return node
    return visit(raw)


def sanitize_pages(raw):
    """Normalize the trainer's storage-HTML export to a REST v2 page collection.

    This is a representation conversion, not a byte-exact HTTP capture.
    """
    clean = sanitize(raw)
    pages = clean.get('pages', clean.get('results', []))
    results = []
    for page in pages:
        item = {key: page[key] for key in ('id', 'title', 'parentId', 'spaceId', 'status', 'version', '_links') if key in page}
        body = page['body']
        item['body'] = {'storage': {'representation': 'storage', 'value': body}} if isinstance(body, str) else body
        results.append(item)
    return {'results': results, '_links': clean.get('_links', {})}


def sanitize_prs(raw):
    """Keep native PR fields and separately exported REST resources intact."""
    return sanitize(raw)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == 'bitbucket':
        parser = argparse.ArgumentParser(description='Sanitize a Bitbucket export and extract Jira remote links')
        parser.add_argument('raw_export', type=Path)
        parser.add_argument('prs', type=Path)
        parser.add_argument('--remote-links', type=Path, required=True)
        args = parser.parse_args(argv[1:])
        paths = [p.resolve() for p in (args.raw_export, args.prs, args.remote_links)]
        if len(set(paths)) != len(paths):
            parser.error('Input and output paths must be distinct')
        clean = sanitize_prs(json.loads(args.raw_export.read_text(encoding='utf-8')))
        links = {}
        for bundle in clean['pull_requests'] + clean.get('other_repo_pull_requests', []):
            for key, values in bundle.get('jira_remote_links', {}).items():
                bucket = links.setdefault(key, [])
                for value in values:
                    if value not in bucket:
                        bucket.append(value)
        for path, document in ((args.prs, clean), (args.remote_links, links)):
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Sanitized Bitbucket export and remote links; raw values were not logged.')
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw_export', type=Path)
    parser.add_argument('tickets', type=Path)
    parser.add_argument('--example', type=Path, required=True)
    parser.add_argument('--example-key', default='TEST-1')
    parser.add_argument('--pages-raw', type=Path)
    parser.add_argument('--pages', type=Path)
    parser.add_argument('--prs-raw', type=Path)
    parser.add_argument('--prs', type=Path)
    args = parser.parse_args(argv)
    if bool(args.pages_raw) != bool(args.pages):
        parser.error('--pages-raw and --pages must be supplied together')
    if bool(args.prs_raw) != bool(args.prs):
        parser.error('--prs-raw and --prs must be supplied together')
    paths = [p.resolve() for p in (args.raw_export, args.tickets, args.example, args.pages_raw, args.pages, args.prs_raw, args.prs) if p]
    if len(set(paths)) != len(paths):
        parser.error('Input and output paths must be distinct')
    clean = sanitize(json.loads(args.raw_export.read_text(encoding='utf-8')))
    issue = next((item for item in clean['issues'] if item['key'] == args.example_key), None)
    if issue is None:
        parser.error('Example key not present in export')
    example = {key: issue[key] for key in ('expand', 'id', 'self', 'key', 'fields')}
    outputs = [(args.tickets, clean), (args.example, example)]
    if args.pages_raw:
        outputs.append((args.pages, sanitize_pages(json.loads(args.pages_raw.read_text(encoding='utf-8')))))
    if args.prs_raw:
        outputs.append((args.prs, sanitize_prs(json.loads(args.prs_raw.read_text(encoding='utf-8')))))
    for path, document in outputs:
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Sanitized {len(clean["issues"])} issues; raw values were not logged.')


if __name__ == '__main__':
    main()
