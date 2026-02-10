from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .models import Issue


@dataclass
class CrawlSnapshot:
    status_code: int
    response_ms: float
    html: str
    final_url: str
    title: str
    meta_description: str
    canonical: str
    meta_robots: str
    h1_count: int
    h2_count: int
    image_without_alt: int
    internal_links: int
    broken_internal_links: int
    https_enabled: bool
    mixed_content_count: int
    word_count: int
    og_title: str
    og_description: str
    hreflang_count: int
    invalid_hreflang_count: int
    robots_disallow_all: bool
    sitemap_ok: bool


def _safe_get(url: str, timeout_seconds: int = 6) -> requests.Response | None:
    try:
        return requests.get(url, timeout=timeout_seconds, headers={"User-Agent": "SEO-Analyzer-Bot/1.0"})
    except Exception:
        return None


def fetch_page(url: str, timeout_seconds: int = 12) -> CrawlSnapshot:
    start = time.perf_counter()
    response = requests.get(url, timeout=timeout_seconds, headers={"User-Agent": "SEO-Analyzer-Bot/1.0"})
    elapsed_ms = (time.perf_counter() - start) * 1000
    final_url = response.url
    parsed = urlparse(final_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    https_enabled = parsed.scheme == "https"

    soup = BeautifulSoup(response.text, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = (meta_tag.get("content") or "").strip() if meta_tag else ""
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical = (canonical_tag.get("href") or "").strip() if canonical_tag else ""
    canonical = urljoin(final_url, canonical) if canonical else ""
    robots_meta = soup.find("meta", attrs={"name": "robots"})
    meta_robots = (robots_meta.get("content") or "").strip().lower() if robots_meta else ""
    h1_count = len(soup.find_all("h1"))
    h2_count = len(soup.find_all("h2"))

    for script in soup(["script", "style", "noscript"]):
        script.decompose()
    word_count = len(soup.get_text(" ", strip=True).split())

    og_title_tag = soup.find("meta", attrs={"property": "og:title"})
    og_desc_tag = soup.find("meta", attrs={"property": "og:description"})
    og_title = (og_title_tag.get("content") or "").strip() if og_title_tag else ""
    og_description = (og_desc_tag.get("content") or "").strip() if og_desc_tag else ""

    hreflang_count = 0
    invalid_hreflang_count = 0
    for link in soup.find_all("link", attrs={"rel": "alternate"}):
        hreflang = (link.get("hreflang") or "").strip()
        if not hreflang:
            continue
        hreflang_count += 1
        is_valid = hreflang == "x-default" or len(hreflang) in (2, 5)
        if not is_valid:
            invalid_hreflang_count += 1

    images = soup.find_all("img")
    image_without_alt = 0
    for image in images:
        alt = image.get("alt")
        if alt is None or not str(alt).strip():
            image_without_alt += 1

    internal_links = 0
    broken_internal_links = 0
    internal_targets: list[str] = []
    for anchor in soup.find_all("a"):
        href = (anchor.get("href") or "").strip()
        if href.startswith("/") or href.startswith(origin):
            internal_links += 1
            absolute = urljoin(final_url, href)
            if absolute not in internal_targets:
                internal_targets.append(absolute)

    for link in internal_targets[:8]:
        link_resp = _safe_get(link, timeout_seconds=6)
        if link_resp is None or link_resp.status_code >= 400:
            broken_internal_links += 1

    mixed_content_count = 0
    if https_enabled:
        for tag in soup.find_all(["img", "script", "iframe", "source", "audio", "video", "link"]):
            attr = "src" if tag.name in {"img", "script", "iframe", "source", "audio", "video"} else "href"
            value = (tag.get(attr) or "").strip()
            if value.startswith("http://"):
                mixed_content_count += 1

    robots_disallow_all = False
    robots_resp = _safe_get(f"{origin}/robots.txt", timeout_seconds=6)
    if robots_resp and robots_resp.status_code == 200:
        user_agent_all = False
        for raw_line in robots_resp.text.splitlines():
            line = raw_line.split("#", 1)[0].strip().lower()
            if not line:
                continue
            if line.startswith("user-agent:"):
                user_agent_all = line.split(":", 1)[1].strip() == "*"
            if user_agent_all and line.startswith("disallow:"):
                rule = line.split(":", 1)[1].strip()
                if rule == "/":
                    robots_disallow_all = True
                    break

    sitemap_ok = False
    sitemap_resp = _safe_get(f"{origin}/sitemap.xml", timeout_seconds=6)
    if sitemap_resp and sitemap_resp.status_code == 200:
        body = sitemap_resp.text.lower()
        sitemap_ok = "<urlset" in body or "<sitemapindex" in body

    return CrawlSnapshot(
        status_code=response.status_code,
        response_ms=round(elapsed_ms, 2),
        html=response.text,
        final_url=final_url,
        title=title,
        meta_description=meta_description,
        canonical=canonical,
        meta_robots=meta_robots,
        h1_count=h1_count,
        h2_count=h2_count,
        image_without_alt=image_without_alt,
        internal_links=internal_links,
        broken_internal_links=broken_internal_links,
        https_enabled=https_enabled,
        mixed_content_count=mixed_content_count,
        word_count=word_count,
        og_title=og_title,
        og_description=og_description,
        hreflang_count=hreflang_count,
        invalid_hreflang_count=invalid_hreflang_count,
        robots_disallow_all=robots_disallow_all,
        sitemap_ok=sitemap_ok,
    )


def run_playwright_audit(url: str) -> dict[str, float]:
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)

            desktop_context = browser.new_context(viewport={"width": 1440, "height": 900})
            desktop_page = desktop_context.new_page()
            desktop_page.goto(url, wait_until="domcontentloaded", timeout=45000)
            desktop_metrics = desktop_page.evaluate(
                """
                () => {
                  const nav = performance.getEntriesByType('navigation')[0];
                  if (!nav) return {dom: 0, load: 0};
                  return {
                    dom: Math.round(nav.domContentLoadedEventEnd),
                    load: Math.round(nav.loadEventEnd)
                  };
                }
                """
            )
            desktop_context.close()

            mobile_context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
            mobile_page = mobile_context.new_page()
            mobile_page.goto(url, wait_until="domcontentloaded", timeout=45000)
            mobile_metrics = mobile_page.evaluate(
                """
                () => {
                  const nav = performance.getEntriesByType('navigation')[0];
                  if (!nav) return {dom: 0, load: 0};
                  return {
                    dom: Math.round(nav.domContentLoadedEventEnd),
                    load: Math.round(nav.loadEventEnd)
                  };
                }
                """
            )
            mobile_context.close()
            browser.close()

            return {
                "playwright_desktop_dom_ms": float(desktop_metrics.get("dom", 0)),
                "playwright_desktop_load_ms": float(desktop_metrics.get("load", 0)),
                "playwright_mobile_dom_ms": float(mobile_metrics.get("dom", 0)),
                "playwright_mobile_load_ms": float(mobile_metrics.get("load", 0)),
            }
    except Exception:
        return {}


def run_lighthouse_audit(url: str) -> dict[str, float]:
    if os.getenv("LIGHTHOUSE_ENABLED", "1") != "1":
        return {}

    command = [
        "npx",
        "lighthouse",
        url,
        "--quiet",
        "--output=json",
        "--output-path=stdout",
        "--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage",
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=240)
        payload = json.loads(result.stdout)
        categories = payload.get("categories", {})
        audits = payload.get("audits", {})
        return {
            "lighthouse_performance_score": float((categories.get("performance", {}).get("score") or 0) * 100),
            "lighthouse_accessibility_score": float((categories.get("accessibility", {}).get("score") or 0) * 100),
            "lighthouse_best_practices_score": float((categories.get("best-practices", {}).get("score") or 0) * 100),
            "lighthouse_seo_score": float((categories.get("seo", {}).get("score") or 0) * 100),
            "lighthouse_lcp_ms": float(audits.get("largest-contentful-paint", {}).get("numericValue") or 0),
            "lighthouse_cls": float(audits.get("cumulative-layout-shift", {}).get("numericValue") or 0),
            "lighthouse_tbt_ms": float(audits.get("total-blocking-time", {}).get("numericValue") or 0),
        }
    except Exception:
        return {}


def _priority_score(impact: str, effort: str, confidence: float) -> float:
    impact_map = {"low": 1.0, "medium": 2.0, "high": 3.0}
    effort_map = {"easy": 1.0, "medium": 2.0, "hard": 3.0}
    return round((impact_map[impact] * confidence) / effort_map[effort], 3)


def build_issues(snapshot: CrawlSnapshot, audit_metrics: dict[str, float] | None = None) -> list[Issue]:
    issues: list[Issue] = []

    if snapshot.status_code >= 400:
        confidence = 1.0
        impact = "high"
        effort = "medium"
        issues.append(
            Issue(
                key="http_status_error",
                title=f"Page returned HTTP {snapshot.status_code}",
                details="Search engines may not index pages with error status codes.",
                severity="critical",
                impact=impact,
                effort=effort,
                fix_suggestion="Fix server or routing issues and return a valid 200 status for canonical pages.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if not snapshot.title:
        confidence = 0.95
        impact = "high"
        effort = "easy"
        issues.append(
            Issue(
                key="missing_title",
                title="Missing <title> tag",
                details="Title tags are core ranking and CTR signals.",
                severity="high",
                impact=impact,
                effort=effort,
                fix_suggestion="Add a unique title tag between 50-60 characters with target keyword intent.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )
    elif len(snapshot.title) < 30 or len(snapshot.title) > 65:
        confidence = 0.9
        impact = "medium"
        effort = "easy"
        issues.append(
            Issue(
                key="title_length",
                title="Title length is outside recommended range",
                details="Very short or long titles reduce clarity and can hurt click-through rate.",
                severity="medium",
                impact=impact,
                effort=effort,
                fix_suggestion="Keep title length around 50-60 characters and match search intent.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if not snapshot.meta_description:
        confidence = 0.9
        impact = "medium"
        effort = "easy"
        issues.append(
            Issue(
                key="missing_meta_description",
                title="Missing meta description",
                details="Meta descriptions affect snippet quality and CTR.",
                severity="medium",
                impact=impact,
                effort=effort,
                fix_suggestion="Add a clear 140-160 character meta description with value proposition and keyword context.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if snapshot.h1_count == 0:
        confidence = 0.9
        impact = "high"
        effort = "easy"
        issues.append(
            Issue(
                key="missing_h1",
                title="Missing H1 heading",
                details="Primary topic heading helps search engines understand page focus.",
                severity="high",
                impact=impact,
                effort=effort,
                fix_suggestion="Add one clear H1 containing primary keyword intent.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )
    elif snapshot.h1_count > 1:
        confidence = 0.8
        impact = "medium"
        effort = "easy"
        issues.append(
            Issue(
                key="multiple_h1",
                title="Multiple H1 headings found",
                details="Multiple H1 tags can dilute page topical focus.",
                severity="low",
                impact=impact,
                effort=effort,
                fix_suggestion="Use one H1 and move additional headings to H2/H3.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if snapshot.image_without_alt > 0:
        confidence = 0.85
        impact = "medium"
        effort = "medium"
        issues.append(
            Issue(
                key="images_missing_alt",
                title=f"{snapshot.image_without_alt} images are missing alt text",
                details="Alt text improves accessibility and image search relevance.",
                severity="medium",
                impact=impact,
                effort=effort,
                fix_suggestion="Add descriptive alt text for meaningful images and keep decorative images empty.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if snapshot.internal_links < 3:
        confidence = 0.7
        impact = "medium"
        effort = "medium"
        issues.append(
            Issue(
                key="few_internal_links",
                title="Low internal link count",
                details="Internal links distribute authority and help crawlers discover key pages.",
                severity="low",
                impact=impact,
                effort=effort,
                fix_suggestion="Add contextual internal links to related high-value pages.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if snapshot.response_ms > 1800:
        confidence = 0.8
        impact = "high"
        effort = "hard"
        issues.append(
            Issue(
                key="slow_response",
                title="Slow server response time",
                details="Slow pages can reduce crawl efficiency and user engagement.",
                severity="high",
                impact=impact,
                effort=effort,
                fix_suggestion="Optimize TTFB with caching, compression, and backend profiling.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if not snapshot.canonical:
        confidence = 0.85
        impact = "medium"
        effort = "easy"
        issues.append(
            Issue(
                key="missing_canonical",
                title="Missing canonical tag",
                details="Canonical helps consolidate indexing signals and avoid duplicates.",
                severity="medium",
                impact=impact,
                effort=effort,
                fix_suggestion="Add a self-referencing canonical URL on indexable pages.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if "noindex" in snapshot.meta_robots:
        confidence = 0.95
        impact = "high"
        effort = "easy"
        issues.append(
            Issue(
                key="noindex_detected",
                title="Meta robots contains noindex",
                details="Noindex prevents search engines from indexing the page.",
                severity="critical",
                impact=impact,
                effort=effort,
                fix_suggestion="Remove noindex from pages that should rank.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if snapshot.robots_disallow_all:
        confidence = 0.95
        impact = "high"
        effort = "easy"
        issues.append(
            Issue(
                key="robots_disallow_all",
                title="robots.txt disallows full site crawl",
                details="Disallow: / for User-agent * can block indexing across the website.",
                severity="critical",
                impact=impact,
                effort=effort,
                fix_suggestion="Update robots.txt rules to allow important content paths.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if not snapshot.sitemap_ok:
        confidence = 0.8
        impact = "medium"
        effort = "easy"
        issues.append(
            Issue(
                key="missing_sitemap",
                title="Sitemap not found or invalid",
                details="XML sitemap helps crawlers discover and prioritize pages.",
                severity="medium",
                impact=impact,
                effort=effort,
                fix_suggestion="Publish a valid sitemap.xml and reference it in robots.txt.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if snapshot.word_count < 250:
        confidence = 0.8
        impact = "medium"
        effort = "medium"
        issues.append(
            Issue(
                key="thin_content",
                title="Low content depth detected",
                details="Thin pages may struggle to rank for competitive queries.",
                severity="medium",
                impact=impact,
                effort=effort,
                fix_suggestion="Expand page with useful, intent-focused content sections.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if snapshot.broken_internal_links > 0:
        confidence = 0.9
        impact = "high"
        effort = "medium"
        issues.append(
            Issue(
                key="broken_internal_links",
                title=f"{snapshot.broken_internal_links} broken internal links found",
                details="Broken internal links waste crawl budget and hurt UX.",
                severity="high",
                impact=impact,
                effort=effort,
                fix_suggestion="Fix or redirect broken internal destinations.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if not snapshot.https_enabled:
        confidence = 0.95
        impact = "high"
        effort = "medium"
        issues.append(
            Issue(
                key="no_https",
                title="Page is not served over HTTPS",
                details="HTTPS is a trust and ranking signal.",
                severity="critical",
                impact=impact,
                effort=effort,
                fix_suggestion="Enable TLS and redirect HTTP to HTTPS site-wide.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if snapshot.mixed_content_count > 0:
        confidence = 0.9
        impact = "medium"
        effort = "easy"
        issues.append(
            Issue(
                key="mixed_content",
                title=f"{snapshot.mixed_content_count} mixed-content resources detected",
                details="HTTP assets on HTTPS pages can trigger security warnings.",
                severity="medium",
                impact=impact,
                effort=effort,
                fix_suggestion="Serve all assets over HTTPS URLs.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if not snapshot.og_title or not snapshot.og_description:
        confidence = 0.75
        impact = "low"
        effort = "easy"
        issues.append(
            Issue(
                key="missing_open_graph",
                title="Open Graph metadata is incomplete",
                details="Social snippets perform better with OG title and description.",
                severity="low",
                impact=impact,
                effort=effort,
                fix_suggestion="Add og:title and og:description tags for social sharing.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    if snapshot.invalid_hreflang_count > 0:
        confidence = 0.8
        impact = "medium"
        effort = "medium"
        issues.append(
            Issue(
                key="invalid_hreflang",
                title=f"{snapshot.invalid_hreflang_count} hreflang values look invalid",
                details="Invalid hreflang can break international targeting.",
                severity="medium",
                impact=impact,
                effort=effort,
                fix_suggestion="Use valid hreflang values like en, en-US, lt, x-default.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    audit_metrics = audit_metrics or {}

    lighthouse_seo = audit_metrics.get("lighthouse_seo_score")
    if lighthouse_seo is not None and lighthouse_seo < 80:
        confidence = 0.85
        impact = "high"
        effort = "medium"
        issues.append(
            Issue(
                key="lighthouse_seo_low",
                title=f"Lighthouse SEO score is low ({int(lighthouse_seo)})",
                details="Automated Lighthouse SEO signals show optimization gaps.",
                severity="high",
                impact=impact,
                effort=effort,
                fix_suggestion="Resolve failing Lighthouse SEO audits and rerun after deployment.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    lighthouse_perf = audit_metrics.get("lighthouse_performance_score")
    if lighthouse_perf is not None and lighthouse_perf < 70:
        confidence = 0.8
        impact = "high"
        effort = "hard"
        issues.append(
            Issue(
                key="lighthouse_performance_low",
                title=f"Lighthouse performance score is low ({int(lighthouse_perf)})",
                details="Poor runtime performance can reduce rankings and user engagement.",
                severity="high",
                impact=impact,
                effort=effort,
                fix_suggestion="Improve LCP/TBT by reducing JS payload, optimizing images, and caching.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    mobile_load = audit_metrics.get("playwright_mobile_load_ms")
    if mobile_load is not None and mobile_load > 4000:
        confidence = 0.75
        impact = "high"
        effort = "medium"
        issues.append(
            Issue(
                key="mobile_slow_load",
                title="Mobile load time is high",
                details="Mobile users are sensitive to load latency and bounce faster.",
                severity="medium",
                impact=impact,
                effort=effort,
                fix_suggestion="Prioritize above-the-fold content and defer non-critical scripts on mobile.",
                confidence=confidence,
                priority_score=_priority_score(impact, effort, confidence),
            )
        )

    return sorted(issues, key=lambda item: item.priority_score, reverse=True)


def calculate_score(issues: list[Issue], status_code: int) -> int:
    score = 100

    if status_code >= 400:
        score -= 50

    for issue in issues:
        if issue.severity == "critical":
            score -= 20
        elif issue.severity == "high":
            score -= 12
        elif issue.severity == "medium":
            score -= 7
        else:
            score -= 3

    return max(score, 0)
