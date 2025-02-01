from urllib.parse import urlparse, urlunparse
import httpx
from bs4 import BeautifulSoup, Tag
from .load_url import load_url, user_agent, _raise_for_status
from typing import Iterator

max_results = 2
banned_sites = {
    # user-generated content, usually doesn't contain much useful text
    'facebook.com',
    'tiktok.com',
    'spotify.com',
    'twitter.com', 'x.com',
    # ai generated bullshit
    'quora.com'
}
result_class = 'yuRUbf'

def web_search(query: str):
    """Performs a web search for the query. Use every time you need to search the Internet."""
    r = httpx.get(f'https://google.com/search', params={'q': query, 'hl': 'en'}, headers={'user-agent': user_agent}, follow_redirects=True)
    _raise_for_status(r)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    results: list[Tag] = soup.find_all(class_=result_class)

    _urls = set()
    def _pages() -> Iterator[tuple[str, str]]:
        for x in results:
            h3 = x.find("h3")
            if not h3:
                continue
            a = h3.parent
            if a.name != "a":
                continue
            title = h3.text
            url = a['href']
            url = urlunparse(urlparse(url)[:-1] + ('',))
            if url in _urls:
                continue
            _urls.add(url)
            yield url, title
        
    response = []
    i = 0
    for url, title in _pages():
        domain = '.'.join(urlparse(url).netloc.split('.')[-2:])
        if domain in banned_sites:
            continue
        try:
            summary = load_url(url)
        except Exception as e:
            continue
        response.append(f"Result #{i+1}\n\n{title}\n{url}\n\n{summary.replace('\n\n', '\n')}")
        i += 1
        if i == max_results:
            break
    
    return "\n\n\n\n".join(response)

if __name__ == "__main__":
    print(web_search(input("> ")))