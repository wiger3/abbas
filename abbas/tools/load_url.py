import os
import json
import itertools
from urllib.parse import urlparse, urlunparse
import httpx
import replicate
from bs4 import BeautifulSoup, Tag
from typing import Optional, Callable

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"

def load_url(url: str, question: Optional[str] = None) -> str:
    """Answers question about content of a website. Use every time the user's message contains a link."""
    if not question: # llama will use "" for no argument instead of None
        question = "Summarize the content of this page"
    return _load_url(url, question)

def _load_url(url: str, question: str) -> str:
    url = _rewrite_url(url)
    text = _fetch(url)

    if len(text) >= 8000:
        raise ValueError(f"Website too long! ({len(text)}/8000)")
    
    output = _answer_question(text.replace('\u2019', "'"), question)
    return output

def _rewrite_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    scheme, netloc, path, params, query, fragment = urlparse(url)
    domain = netloc.split('.')
    if domain[-2:] == ['reddit', 'com']:
        if len(domain) == 2 or domain[0] != 'old':
            netloc = 'old.reddit.com'
    if domain[-2:] == ['youtube', 'com']:
        if path == '/watch':
            query = dict(x.split('=') for x in query.split('&'))
            v = query['v']
            netloc, path = 'watch', f'/{v}'
        else:
            path = path.split('/')[1:]
            if path[0] == 'c' or path[0] == 'user':
                netloc = 'user'
                channel = path[1]
            elif path[0] == 'channel':
                netloc = 'channel'
                channel = path[1]
            elif path[0].startswith('@'):
                netloc = 'handle'
                channel = path[0][1:]
            else:
                netloc = 'user'
                channel = path[0]
            path = f'/{channel}'
        scheme, query = 'youtube', ''
    params, fragment = '', ''
    
    return urlunparse((scheme, netloc, path, params, query, fragment))

def _fetch(url: str) -> str:
    if url.startswith("youtube://"):
        return _fetch_youtube(url)
    r = httpx.get(url, headers={'user-agent': user_agent, 'accept-language': 'en;q=0.9,*;q=0.5'}, follow_redirects=True)
    _raise_for_status(r)
    soup = BeautifulSoup(r.text, 'lxml')
    parser = _get_parser(url)
    text = parser(soup)
    return text

def _fetch_youtube(url: str) -> str:
    key = os.getenv("GOOGLE_APIKEY")
    path = url.split('/')[2:]
    if path[0] == 'watch':
        url = "https://www.googleapis.com/youtube/v3/videos"
        r = httpx.get(url, params={'part': 'snippet', 'id': path[1], 'maxResults': 1, 'key': key})
        _raise_for_status(r)
        response = json.loads(r.text)
        video = response['items'][0]['snippet']
        title = video['title']
        description = video['description']
        author = video['channelTitle']
        return f"YouTube video\n\nTitle: {title}\nAuthor: {author}\nDescription:\n{description.replace('\n\n', '\n')}"[:8000]
    else:
        data = {'part': 'snippet,statistics,contentDetails', 'maxResults': 1, 'key': key}
        match path[0]:
            case 'channel':
                data['id'] = path[1]
            case 'user':
                data['forUsername'] = path[1]
            case 'handle':
                data['forHandle'] = path[1]
            case _:
                raise ValueError("Incorrect youtube path: " + path[0]) # should never happen
        url = "https://www.googleapis.com/youtube/v3/channels"
        r = httpx.get(url, params=data)
        _raise_for_status(r)
        response = json.loads(r.text)

        channel = response['items'][0]['snippet']
        channel.update(response['items'][0]['statistics'])
        title = channel['title']
        description = channel['description']
        subscribers = channel['subscriberCount']
        uploads = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        url = "https://www.googleapis.com/youtube/v3/playlistItems"
        r = httpx.get(url, params={'part': 'snippet', 'playlistId': uploads, 'maxResults': 5, 'key': key})
        _raise_for_status(r)
        response = json.loads(r.text)
        uploads = response['items']
        if len(uploads) == 0:
            uploads_text = "This channel has no videos."
        else:
            uploads_text = f"Last {len(uploads)} videos (latest to oldest):\n"
            uploads_text += "\n".join(x['snippet']['title'] for x in uploads)
        
        return f"YouTube channel\n\nTitle: {title}\nSubscriber count: {subscribers}\nDescription:\n{description.replace('\n\n', '\n')}\n\n{uploads_text}"[:8000]

def _get_parser(url: str) -> Callable:
    domain = urlparse(url).netloc.split('.')
    if domain[-3:] == ['old', 'reddit', 'com']:
        return _parser_reddit
    if domain[-2:] == ['wikipedia', 'org']:
        return _parser_wikipedia
    return _parser_default

def _parser_default(soup: BeautifulSoup):
    main = soup.find_all("main") or soup.find_all(role="main")
    for x in soup.find_all("article"):
        if not set(main) & set(x.parents):
            main.append(x)
    if not main:
        main = [soup]
    text = "\n\n".join(x.get_text("\n", strip=True) for x in main)
    return text

def _parser_reddit(soup: BeautifulSoup, max_length = 8000):
    title = soup.find("p", class_="title").find("a")
    tagline = soup.find("p", class_="tagline").text
    expando = soup.find("div", class_="expando")
    if expando:
        media = expando.find(class_="media-preview")
        if media:
            video = media.find("video")
            img = media.find("img")
            if video:
                submission = "[video]"
            elif img:
                submission = "[image]"
            else:
                submission = "[media]"
        else:
            submission = expando.text.strip()
    else:
        submission = "[no content]"
        if title.has_attr('href'):
            href = title['href']
            parsed = urlparse(href)
            if parsed.netloc == 'preview.redd.it':
                parsed.netloc = 'i.redd.it'
                parsed.query = ''
                href = urlunparse(parsed)
            try:
                r = httpx.head(href, headers={'user-agent': user_agent}, follow_redirects=True).raise_for_status()
                if 'content-type' in r.headers:
                    content_type = r.headers['content-type']
                    if content_type == 'text/plain':
                        r = httpx.get(href, headers={'user-agent': user_agent}, follow_redirects=True).raise_for_status()
                        submission = r.text.strip()
                    else:
                        content_type = content_type.split('/', 1)[0]
                        if content_type in ('image', 'video'):
                            submission = f"[{content_type}]"
            except httpx.HTTPError:
                pass
                
    
    title = title.text
    text = f"{title}\n{tagline}\n{submission}\n\n"

    i = 0
    def parse_comments(elem: Tag, parent_id: int = 0):
        threads = [parse_comment(x, parent_id) for x in elem.find(class_="sitetable").find_all(class_="comment", recursive=False)]
        comments = list(itertools.chain.from_iterable(threads))
        return comments
    def parse_comment(elem: Tag, parent_id: int):
        nonlocal i
        i += 1
        author_elem = elem.find(class_="author")
        text_elem = elem.find(class_="md")
        score_elem = elem.find(class_="tagline").find(class_="unvoted")
        if not text_elem or not score_elem:
            return []
        comment_author = author_elem.text if author_elem else "[deleted]"
        comment_text = "\n".join(p.text for p in text_elem.find_all("p")).strip()
        comment_score = int(score_elem['title'])
        result = [{'id': i, 'author': comment_author, 'text': comment_text, 'score': comment_score, 'parent': parent_id}]

        child = elem.find(class_="child")
        if child.contents:
            result += parse_comments(child, i)
        
        return result

    comments = parse_comments(soup.find(class_="commentarea"))
    
    # remove least important comments (lowest rated, without children) to get under the character limit
    template_len = len('<comment author="">\n\n</comment>\n')
    while len(text) + template_len * len(comments) + len(''.join(comment['author'] + comment['text'] for comment in comments)) > max_length:
        parents = {x['parent'] for x in comments}
        childless = (x for x in comments if x['id'] not in parents)
        worst = min(childless, key=lambda x: x['score'])
        comments.remove(worst)

    def serialize_comments(parent_id = 0):
        return ''.join(serialize_comment(comment) for comment in filter(lambda x: x['parent']==parent_id, comments))
    def serialize_comment(comment):
        children = serialize_comments(comment['id'])
        return f"<comment author=\"{comment['author']}\">\n{comment['text']}\n{children}</comment>\n"
    
    text += serialize_comments()
    return text

def _parser_wikipedia(soup: BeautifulSoup, max_length = 8000):
    title = soup.find(class_="mw-page-title-main").text.strip()
    sitesub = soup.find(id="siteSub").text.strip()
    content = soup.find(id="mw-content-text").find(class_="mw-parser-output")

    sections = {}
    para = ['_']

    for elem in content.children:
        if elem.name == 'div' and elem.has_attr('class') and 'mw-heading2' in elem['class']:
            text = '\n'.join(para[1:])
            sections[para[0]] = text.strip()
            para = [elem.find('h2').text.strip()]
            continue
        if elem.name == 'p':
            for sup in elem.find_all('sup'):
                sup.decompose()
            para.append(elem.text.strip())
            continue
    
    sections = {k: v for k, v in sections.items() if v}
    text = f"{title}\n{sitesub}\n\n{sections.pop('_')}"
    
    if len(text) > max_length:
        # raise error if we can't even insert the introduction
        raise ValueError("Wikipedia article is too long to summarize!")
    
    for k, v in sections.items():
        subtext = f"\n\n{k}\n\n{v}"
        if len(text + subtext) > max_length:
            break
        text += subtext
    
    return text

def _answer_question(text: str, question: str) -> str:
    system_prompt = "The user provides a question and a website's text. You analyze the text and answer the question."
    prefix = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
    suffix = f"<|start_header_id|>assistant<|end_header_id|>\n\n"
    prompt = f"Question: {question}\n\n{text}"

    input = {
        "prompt": prompt,
        "prompt_template": f"{prefix}{{prompt}}{suffix}"
    }
    
    output = replicate.run(
        "meta/meta-llama-3-70b-instruct",
        input
    )
    return "".join(output)

def _raise_for_status(response: httpx.Response):
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise httpx.HTTPStatusError(f"{response.status_code} {response.reason_phrase}. Do not repeat this request.", request=e._request, response=e.response)