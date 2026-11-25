"""Static publication contracts: current release only, local assets and real links."""
from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'docs'
RELEASE = 'v3.6.1'


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.elements=[];self.feed(text)
    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_page_brand_assets_anchors_and_downloads():
    text=(SITE/'index.html').read_text();page=Page(text)
    assert '<title>Ai clipping PRO' in text
    ids=[attrs['id'] for _,attrs in page.elements if 'id' in attrs]
    assert len(ids)==len(set(ids))
    assets=[]
    for tag,attrs in page.elements:
        if tag=='a' and attrs.get('href','').startswith('#'):
            assert attrs['href'][1:] in ids
        for name in ('src','href'):
            value=attrs.get(name,'')
            if value and not value.startswith(('https:','#','data:')):
                assert (SITE/value).is_file(), value
        if 'data-asset' in attrs:
            assert f'/releases/download/{RELEASE}/' in attrs['href']
            assets.append(attrs['data-asset'])
        if tag=='img':assert 'alt' in attrs
    assert len(set(assets))==7
    assert 'v1.1.0' not in text
    assert 'Concept illustration' not in text
    assert 'bounded tools' in ' '.join(text.split())


def test_readme_is_current_release_only_and_no_script_interactivity():
    text=(ROOT/'README.md').read_text()
    assert set(re.findall(r'v\d+\.\d+\.\d+',text))=={RELEASE}
    assert not re.search(r'(?i)<script|onclick=',text)
    assert text.count('<details>')>=4 and text.count('<details>')==text.count('</details>')
    assert 'cross-dissolves' in text
    assert 'Live Gemma quality acceptance was **not verified' in text
    for image in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',text):assert (ROOT/image).is_file()


def test_site_has_no_remote_runtime_or_download_discovery_dependency():
    script=(SITE/'site.js').read_text();css=(SITE/'style.css').read_text()
    assert 'fetch(' not in script and 'releases/latest' not in script
    assert 'prefers-reduced-motion' in css and 'prefers-reduced-motion' in script
    assert 'aria-selected' in script and 'ArrowRight' in script
    assert 'Clipboard unavailable' in script
    assert not re.search(r'https?://',css)
