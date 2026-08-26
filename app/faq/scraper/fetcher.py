import re

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.sync_api import sync_playwright
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

STRIP_TAGS = {
    "script", "style", "nav", "footer", "header", "noscript",
    "svg", "iframe", "img", "picture", "form", "button",
    "input", "select", "textarea", "aside",
}
BLOCK_TAGS = {"p", "ul", "ol", "li", "h1", "h2", "h3", "h4", "table", "div"}
INLINE_TAGS = {"div", "span", "section", "article"}


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
)
def fetch_url(url: str) -> str:
    with sync_playwright() as p:
        browser = None
        for channel in (None, "chrome", "msedge"):
            try:
                browser = p.chromium.launch(headless=True, **({} if channel is None else {"channel": channel}))
                break
            except Exception:
                continue
        if browser is None:
            raise RuntimeError("No usable browser found. Run: playwright install chromium")
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        html = page.content()
        browser.close()
        return html


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    for a in soup.find_all("a"):
        a.unwrap()
    for tag in soup.find_all(True):
        text = tag.get_text(separator=" ", strip=True)
        has_block_child = any(c.name in BLOCK_TAGS for c in tag.children if hasattr(c, "name"))
        if tag.name in INLINE_TAGS and not has_block_child and len(text) < 60:
            tag.unwrap()
    return str(soup)


def html_to_markdown(html: str) -> str:
    content = md(html, heading_style="ATX")
    content = re.sub(r'!\[.*?\]\(.*?\)', "", content)
    content = re.sub(r'https?://\S+', "", content)
    content = re.sub(r'\n{3,}', "\n\n", content)
    content = re.sub(r'^\*\s+(#{1,6}\s+)', r'\1', content, flags=re.MULTILINE)
    content = re.sub(
        r'^((?:Mr|Ms|Mrs|Dr)\. [A-Z][^\n]{3,60}\(\d{2} years\)[^\n]*)',
        r'#### \1',
        content, flags=re.MULTILINE,
    )
    return content.strip()
