import json
import os
import re
from typing import Any
from urllib import request, error


class FirecrawlSourcingSubAgent:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY") or ""
        self.base_url = (base_url or os.getenv("FIRECRAWL_BASE_URL") or "https://api.firecrawl.dev/v1").rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.api_key.strip())

    def scrape_urls(self, urls: list[str], max_urls: int = 10, timeout_seconds: int = 30) -> list[dict[str, Any]]:
        if not self.is_configured():
            raise RuntimeError("FIRECRAWL_API_KEY is not configured")

        clean_urls = []
        for raw_url in urls:
            candidate = str(raw_url or "").strip()
            if not candidate:
                continue
            if not re.match(r"^https?://", candidate, flags=re.IGNORECASE):
                continue
            clean_urls.append(candidate)

        unique_urls = []
        seen = set()
        for url in clean_urls:
            key = url.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_urls.append(url)

        results = []
        for index, url in enumerate(unique_urls[: max(1, max_urls)], start=1):
            scraped = self._scrape_single_url(url, timeout_seconds=timeout_seconds)
            markdown = str(scraped.get("markdown") or "").strip()
            title = str(scraped.get("title") or "").strip() or self._title_from_url(url)
            summary = self._compact_text(markdown, limit=1400)

            if not summary:
                continue

            results.append(
                {
                    "candidate_id": index,
                    "full_name": title,
                    "location": "",
                    "skills": [],
                    "summary": summary,
                    "source_profile_url": url,
                }
            )

        return results

    def _scrape_single_url(self, url: str, timeout_seconds: int = 30) -> dict[str, Any]:
        body = json.dumps(
            {
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
            }
        ).encode("utf-8")

        req = request.Request(
            f"{self.base_url}/scrape",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            with request.urlopen(req, timeout=max(5, timeout_seconds)) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                payload = json.loads(raw)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Firecrawl HTTP {exc.code}: {detail[:240]}")
        except Exception as exc:
            raise RuntimeError(f"Firecrawl request failed: {str(exc)}")

        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict):
            return {
                "markdown": data.get("markdown") or "",
                "title": (data.get("metadata") or {}).get("title") or data.get("title") or "",
            }

        return {"markdown": "", "title": ""}

    def _title_from_url(self, url: str) -> str:
        cleaned = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
        cleaned = cleaned.strip("/")
        last_part = cleaned.split("/")[-1] if cleaned else "Candidate Profile"
        last_part = re.sub(r"[-_]+", " ", last_part).strip()
        return last_part.title() if last_part else "Candidate Profile"

    def _compact_text(self, text: str, limit: int = 1400) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit].rsplit(" ", 1)[0] + "..."
