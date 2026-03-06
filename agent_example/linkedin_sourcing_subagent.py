import json
import os
import re
from typing import Any

from openai import OpenAI


class LinkedInSourcingSubAgent:
    def __init__(self, base_url: str | None = None, model: str | None = None, api_key: str | None = None):
        resolved_base_url = (base_url or os.getenv("PARSING_AGENT_BASE_URL") or "http://127.0.0.1:1234").rstrip("/")
        if not resolved_base_url.endswith("/v1"):
            resolved_base_url = f"{resolved_base_url}/v1"
        self.base_url = resolved_base_url
        self.model = model or os.getenv("PARSING_AGENT_MODEL") or "meta-llama-3-8b-instruct"
        self.api_key = api_key or os.getenv("PARSING_AGENT_API_KEY") or "lm-studio"
        try:
            self.request_timeout = float(
                os.getenv("LINKEDIN_SOURCING_TIMEOUT_SECONDS")
                or os.getenv("PARSING_AGENT_TIMEOUT_SECONDS")
                or "12"
            )
        except Exception:
            self.request_timeout = 12.0
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def rank_candidates(self, keyword: str, candidates: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
        clean_keyword = str(keyword or "").strip()
        if not clean_keyword or not candidates:
            return []

        payload_candidates = []
        for item in candidates[:60]:
            payload_candidates.append({
                "candidate_id": item.get("candidate_id"),
                "full_name": item.get("full_name"),
                "location": item.get("location"),
                "skills": item.get("skills") or [],
                "summary": str(item.get("summary") or "")[:500],
                "source_profile_url": item.get("source_profile_url") or "",
            })

        system_prompt = (
            "You are a recruiting sourcing assistant. Rank candidate relevance to the keyword. "
            "Return ONLY valid JSON array where each item has keys: candidate_id, score, rationale. "
            "score must be integer 0..100."
        )
        user_prompt = json.dumps({"keyword": clean_keyword, "candidates": payload_candidates}, ensure_ascii=False)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt[:24000]},
                ],
                temperature=0.1,
                timeout=self.request_timeout,
            )
        except Exception:
            return self._fallback_rank(clean_keyword, payload_candidates, top_k=top_k)

        raw_content = (response.choices[0].message.content or "").strip()
        parsed = self._try_parse_json_array(raw_content)
        if not parsed:
            return self._fallback_rank(clean_keyword, payload_candidates, top_k=top_k)

        score_by_id: dict[int, dict[str, Any]] = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            candidate_id = item.get("candidate_id")
            if not isinstance(candidate_id, int):
                continue
            score = int(item.get("score") or 0)
            rationale = str(item.get("rationale") or "").strip() or "LLM relevance ranking"
            score_by_id[candidate_id] = {
                "candidate_id": candidate_id,
                "score": max(0, min(score, 100)),
                "rationale": rationale,
            }

        ranked = []
        for candidate in payload_candidates:
            candidate_id = candidate.get("candidate_id")
            if not isinstance(candidate_id, int):
                continue
            scored = score_by_id.get(candidate_id)
            if scored:
                ranked.append(scored)

        if not ranked:
            return self._fallback_rank(clean_keyword, payload_candidates, top_k=top_k)

        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked[: max(1, top_k)]

    def _fallback_rank(self, keyword: str, candidates: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
        keyword_tokens = self._extract_keywords(keyword)
        results = []
        for candidate in candidates:
            content = " ".join([
                str(candidate.get("full_name") or ""),
                " ".join([str(s) for s in (candidate.get("skills") or [])]),
                str(candidate.get("summary") or ""),
            ]).lower()
            content_tokens = self._extract_keywords(content)
            overlap = sorted(keyword_tokens.intersection(content_tokens))
            base = 20 if keyword.lower() in content else 0
            score = min(100, base + len(overlap) * 15)
            results.append({
                "candidate_id": candidate.get("candidate_id"),
                "score": score,
                "rationale": f"Keyword overlap: {', '.join(overlap[:6])}" if overlap else "No strong keyword overlap",
            })

        results.sort(key=lambda x: int(x.get("score") or 0), reverse=True)
        return results[: max(1, top_k)]

    def _extract_keywords(self, text: str) -> set[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", (text or "").lower())
        stop_words = {
            "the", "and", "for", "with", "from", "that", "this", "have", "has", "are", "was", "were",
            "candidate", "job", "role", "skills", "skill", "linkedin",
        }
        return {token for token in tokens if token not in stop_words}

    def _try_parse_json_array(self, raw_content: str) -> list[dict[str, Any]] | None:
        if not raw_content:
            return None

        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

        fenced_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", raw_content, flags=re.IGNORECASE)
        if fenced_match:
            fenced_payload = fenced_match.group(1).strip()
            try:
                parsed = json.loads(fenced_payload)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass

        start = raw_content.find("[")
        end = raw_content.rfind("]")
        if start != -1 and end != -1 and end > start:
            sliced_payload = raw_content[start:end + 1]
            try:
                parsed = json.loads(sliced_payload)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass

        return None
