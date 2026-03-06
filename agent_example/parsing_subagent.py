import io
import json
import os
import re
from typing import Any

from openai import OpenAI


class ParsingSubAgent:
    def __init__(self, base_url: str | None = None, model: str | None = None, api_key: str | None = None):
        resolved_base_url = (base_url or os.getenv("PARSING_AGENT_BASE_URL") or "http://127.0.0.1:1234").rstrip("/")
        if not resolved_base_url.endswith("/v1"):
            resolved_base_url = f"{resolved_base_url}/v1"
        self.base_url = resolved_base_url
        self.model = model or os.getenv("PARSING_AGENT_MODEL") or "meta-llama-3-8b-instruct"
        self.api_key = api_key or os.getenv("PARSING_AGENT_API_KEY") or "lm-studio"
        try:
            self.request_timeout = float(os.getenv("PARSING_AGENT_TIMEOUT_SECONDS", "12"))
        except Exception:
            self.request_timeout = 12.0
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def parse_pdf_bytes(self, content_bytes: bytes, filename: str = "") -> dict[str, Any]:
        text = self._extract_pdf_text(content_bytes)
        return self.parse_resume_text(text, filename)

    def parse_resume_text(self, text: str, filename: str = "") -> dict[str, Any]:
        system_prompt = (
            "You are a CRM parsing agent. Extract lead info from this text. "
            "Return ONLY valid JSON with keys: full_name, email, phone, location_city, "
            "location_country, skills (array), languages (array), summary."
        )
        user_content = f"filename: {filename}\n\n{text}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content[:12000]},
            ],
            temperature=0.1,
            timeout=self.request_timeout,
        )

        raw_content = (response.choices[0].message.content or "").strip()
        parsed = self._try_parse_json_object(raw_content)
        if isinstance(parsed, dict):
            return self._normalize_profile(parsed)

        return {
            "full_name": "",
            "email": "",
            "phone": "",
            "location_city": "",
            "location_country": "",
            "skills": [],
            "languages": [],
            "summary": raw_content,
        }

    def parse_csv_text(self, csv_text: str, filename: str = "") -> list[dict[str, Any]]:
        system_prompt = (
            "You are a CRM parsing agent for CSV data. "
            "Return ONLY valid JSON array. Each item must contain keys: "
            "full_name, email, phone, location_city, location_country, skills (array), languages (array), summary."
        )
        user_content = f"filename: {filename}\n\n{csv_text[:20000]}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            timeout=self.request_timeout,
        )

        raw_content = (response.choices[0].message.content or "").strip()
        parsed_rows = self._try_parse_json_array(raw_content)
        if isinstance(parsed_rows, list):
            normalized_rows = []
            for item in parsed_rows:
                if isinstance(item, dict):
                    normalized_rows.append(self._normalize_profile(item))
            return normalized_rows

        return []

    def _try_parse_json_object(self, raw_content: str) -> dict[str, Any] | None:
        if not raw_content:
            return None

        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_content, flags=re.IGNORECASE)
        if fenced_match:
            fenced_payload = fenced_match.group(1).strip()
            try:
                parsed = json.loads(fenced_payload)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        start = raw_content.find("{")
        end = raw_content.rfind("}")
        if start != -1 and end != -1 and end > start:
            sliced_payload = raw_content[start:end + 1]
            try:
                parsed = json.loads(sliced_payload)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        return None

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

    def _extract_pdf_text(self, content_bytes: bytes) -> str:
        try:
            try:
                from pypdf import PdfReader  # type: ignore
            except Exception:
                from PyPDF2 import PdfReader  # type: ignore

            reader = PdfReader(io.BytesIO(content_bytes))
            pages: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.append(page_text)
            return "\n".join(pages)
        except Exception:
            return ""

    def _normalize_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        skills = payload.get("skills") if isinstance(payload.get("skills"), list) else []
        languages = payload.get("languages") if isinstance(payload.get("languages"), list) else []
        return {
            "full_name": str(payload.get("full_name") or "").strip(),
            "email": str(payload.get("email") or "").strip(),
            "phone": str(payload.get("phone") or "").strip(),
            "location_city": str(payload.get("location_city") or "").strip(),
            "location_country": str(payload.get("location_country") or "").strip(),
            "skills": [str(item).strip() for item in skills if str(item).strip()],
            "languages": [str(item).strip() for item in languages if str(item).strip()],
            "summary": str(payload.get("summary") or "").strip(),
        }


def parsing_sub_agent(crm_data: str, base_url: str | None = None, model: str | None = None) -> str:
    agent = ParsingSubAgent(base_url=base_url, model=model)
    response = agent.client.chat.completions.create(
        model=agent.model,
        messages=[
            {"role": "system", "content": "You are a CRM parsing agent. Extract lead info from this text."},
            {"role": "user", "content": crm_data},
        ],
        temperature=0.1,
        timeout=agent.request_timeout,
    )
    return response.choices[0].message.content or ""