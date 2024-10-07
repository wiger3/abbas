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
        if path.startswith('/c/'):
            path = path[2:]
        if query:
            query += '&hl=en'
        else:
            query = '?hl=en'
    fragment = ''
    
    return urlunparse((scheme, netloc, path, params, query, fragment))

def _fetch(url: str) -> str:
    r = httpx.get(url, headers={'user-agent': user_agent}, follow_redirects=True)
    _raise_for_status(r)
    soup = BeautifulSoup(r.text, 'html.parser')
    parser = _get_parser(url)
    text = parser(soup)
    return text

def _get_parser(url: str) -> Callable:
    domain = urlparse(url).netloc.split('.')
    if domain[-3:] == ['old', 'reddit', 'com']:
        return _parser_reddit
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
    title = soup.find("p", class_="title").text
    tagline = soup.find("p", class_="tagline").text
    submission = soup.find("div", class_="expando").text.strip()

    text = f"{title}\n{tagline}\n{submission}"

    i = 0
    def parse_comments(elem: Tag, parent_id: int = 0):
        threads = [parse_comment(x, parent_id) for x in elem.find(class_="sitetable").find_all(class_="comment", recursive=False)]
        comments = list(itertools.chain.from_iterable(threads))
        return comments
    def parse_comment(elem: Tag, parent_id: int):
        nonlocal i
        i += 1
        author_elem = elem.find(class_="author")
        comment_author = author_elem.text if author_elem else "[deleted]"
        comment_text = "\n".join(p.text for p in elem.find(class_="md").find_all("p")).strip()
        comment_score = int(elem.find(class_="tagline").find(class_="unvoted")['title'])
        result = [{'id': i, 'author': comment_author, 'text': comment_text, 'score': comment_score, 'parent': parent_id}]

        child = elem.find(class_="child")
        if child.contents:
            result += parse_comments(child, i)
        
        return result

    comments = parse_comments(soup.find(class_="commentarea"))
    
    # remove least important comments (lowest rated, without children) to get under the character limit
    template_len = len('<comment author="">\n\n</comment>\n')
    while template_len * len(comments) + len(''.join(comment['author'] + comment['text'] for comment in comments)) > max_length:
        parents = {x['parent'] for x in comments}
        childless = (x for x in comments if x['id'] not in parents)
        worst = min(childless, key=lambda x: x['score'])
        comments.remove(worst)

    def serialize_comments(parent_id = 0):
        return ''.join(serialize_comment(comment) for comment in filter(lambda x: x['parent']==parent_id, comments))
    def serialize_comment(comment):
        children = serialize_comments(comment['id'])
        return f"<comment author=\"{comment['author']}\">\n{comment['text']}\n{children}</comment>\n"
    
    text = serialize_comments()
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