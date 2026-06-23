import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import OrderedDict

from detect_secrets.plugins.openai import OpenAIDetector
from detect_secrets.plugins.jwt import JwtTokenDetector
from detect_secrets.plugins.private_key import PrivateKeyDetector
from detect_secrets.plugins.high_entropy_strings import (
    Base64HighEntropyString,
    HexHighEntropyString,
)
from detect_secrets.plugins.aws import AWSKeyDetector
from detect_secrets.plugins.github_token import GitHubTokenDetector
from detect_secrets.plugins.ip_public import IPPublicDetector
from detect_secrets.plugins.artifactory import ArtifactoryDetector
from detect_secrets.plugins.discord import DiscordBotTokenDetector
from detect_secrets.plugins.gitlab_token import GitLabTokenDetector
from detect_secrets.plugins.stripe import StripeDetector
from detect_secrets.plugins.twilio import TwilioKeyDetector
from detect_secrets.plugins.slack import SlackDetector

import scrubadub


PLACEHOLDER_RE = re.compile(r'\[SCRUBBED_([A-Z_]+)_(\d+)\]')


def _placeholder(typ: str, n: int) -> str:
    return f'[SCRUBBED_{typ}_{n}]'


def _iter_scrubadub_filth(text: str):
    """Yield (beg, end, text, type_name) from scrubadub."""
    s = scrubadub.Scrubber()
    for f in s.iter_filth(text):
        detector_name = getattr(f, 'detector_name', 'unknown')
        yield f.beg, f.end, f.text, detector_name.upper()


class _Span:
    __slots__ = ('start', 'end', 'original', 'typ')
    def __init__(self, start: int, end: int, original: str, typ: str):
        self.start = start
        self.end = end
        self.original = original
        self.typ = typ
    def __repr__(self):
        return f'_Span({self.start}:{self.end} {self.typ}={self.original!r})'


class Scrubber:
    """Combines detect-secrets + scrubadub + custom patterns for secret/PII redaction.

    Usage:
        scrubber = Scrubber()
        scrubbed, mapping = scrubber.scrub("My key is sk-xxx and email is user@example.com")
        original = scrubber.unscrub(scrubbed, mapping)
    """

    # Custom patterns covering gaps in detect-secrets/scrubadub
    _CUSTOM_PATTERNS: List[Tuple[str, re.Pattern]] = [
        ("ANTHROPIC_KEY", re.compile(r'\bsk-ant-[a-zA-Z0-9-_]{40,}\b')),
        ("ANTHROPIC_KEY", re.compile(r'\bsk-ant-[a-zA-Z0-9-_]{90,}\b')),
        ("API_KEY", re.compile(r'\bsk-[a-zA-Z0-9-_]{15,}\b')),
        ("JWT", re.compile(r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}')),
        ("PASSWORD", re.compile(r'''(?i)(?:password|passwd|pwd)\s*[:=]\s*['"][^'"]+['"]''')),
        ("PASSWORD", re.compile(r'''(?i)(?:password|passwd|pwd)\s*[:=]\s*\S+''')),
    ]

    # Hosts whose request/response bodies should be scrubbed
    SCRUBBED_HOSTS = {
        "api.openai.com",
        "api.anthropic.com",
        "api.groq.com",
        "api.deepseek.com",
        "api.mistral.ai",
        "api.cohere.ai",
        "api.together.xyz",
        "generativelanguage.googleapis.com",
    }

    def __init__(self):
        self._ds_plugins = [
            OpenAIDetector(),
            JwtTokenDetector(),
            PrivateKeyDetector(),
            Base64HighEntropyString(4.5),
            HexHighEntropyString(3.0),
            AWSKeyDetector(),
            GitHubTokenDetector(),
            IPPublicDetector(),
            ArtifactoryDetector(),
            DiscordBotTokenDetector(),
            GitLabTokenDetector(),
            StripeDetector(),
            TwilioKeyDetector(),
            SlackDetector(),
        ]
        self._counter: Dict[str, int] = {}

    def _next_id(self, typ: str) -> int:
        self._counter[typ] = self._counter.get(typ, 0) + 1
        return self._counter[typ]

    def _find_spans(self, text: str) -> List[_Span]:
        """Find all sensitive spans in text using all detectors."""
        spans: List[_Span] = []

        # 1. detect-secrets plugins
        for plugin in self._ds_plugins:
            try:
                secrets = plugin.analyze_line('input.txt', text, 1)
            except Exception:
                continue
            for s in secrets:
                val = s.secret_value
                if not val:
                    continue
                idx = text.find(val)
                if idx >= 0:
                    spans.append(_Span(idx, idx + len(val), val, s.type.upper().replace(' ', '_')))

        # 2. scrubadub (PII)
        for beg, end, val, typ in _iter_scrubadub_filth(text):
            spans.append(_Span(beg, end, val, typ))

        # 3. custom patterns
        for typ, pattern in self._CUSTOM_PATTERNS:
            for m in pattern.finditer(text):
                spans.append(_Span(m.start(), m.end(), m.group(), typ))

        return spans

    def _resolve_spans(self, spans: List[_Span]) -> List[_Span]:
        """Sort spans by start position, keep the longer one when overlapping."""
        if not spans:
            return []
        spans.sort(key=lambda s: (s.start, -s.end))
        resolved: List[_Span] = []
        for s in spans:
            if not resolved or s.start >= resolved[-1].end:
                resolved.append(s)
            elif s.end > resolved[-1].end:
                resolved[-1].end = s.end
                resolved[-1].original = s.original
        return resolved

    def scrub(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Scrub sensitive data from text.

        Returns (scrubbed_text, {placeholder: original_value}).
        Use unscrub() to restore originals.
        """
        if not text:
            return text, {}

        spans = self._find_spans(text)
        spans = self._resolve_spans(spans)

        if not spans:
            return text, {}

        mapping: Dict[str, str] = {}
        parts: List[str] = []
        pos = 0

        for s in spans:
            if s.start > pos:
                parts.append(text[pos:s.start])
            ph = _placeholder(s.typ, self._next_id(s.typ))
            mapping[ph] = s.original
            parts.append(ph)
            pos = s.end

        if pos < len(text):
            parts.append(text[pos:])

        return ''.join(parts), mapping

    def unscrub(self, text: str, mapping: Dict[str, str]) -> str:
        """Restore original values from placeholders."""
        if not text or not mapping:
            return text

        # Sort by placeholder length (longest first) to avoid partial replacement
        items = sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True)
        for placeholder, original in items:
            text = text.replace(placeholder, original)
        return text

    def scrub_dict(self, obj: Any, mapping: Optional[Dict[str, str]] = None) -> Tuple[Any, Dict[str, str]]:
        """Recursively scrub all string values in a JSON-like structure.

        Preserves structure while replacing sensitive strings with placeholders.
        """
        if mapping is None:
            mapping = {}
        if isinstance(obj, dict):
            return {k: self.scrub_dict(v, mapping)[0] for k, v in obj.items()}, mapping
        elif isinstance(obj, list):
            return [self.scrub_dict(v, mapping)[0] for v in obj], mapping
        elif isinstance(obj, str):
            scrubbed, local_map = self.scrub(obj)
            mapping.update(local_map)
            return scrubbed, mapping
        return obj, mapping

    def unscrub_dict(self, obj: Any, mapping: Dict[str, str]) -> Any:
        """Recursively restore placeholders in a JSON-like structure."""
        if isinstance(obj, dict):
            return {k: self.unscrub_dict(v, mapping) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.unscrub_dict(v, mapping) for v in obj]
        elif isinstance(obj, str):
            return self.unscrub(obj, mapping)
        return obj

    def should_scrub_host(self, host: str) -> bool:
        """Check if a host should be scrubbed."""
        host = host.lower().split(':')[0]
        for h in self.SCRUBBED_HOSTS:
            if host == h or host.endswith('.' + h):
                return True
        return False


_DEFAULT_SCRUBBER = None


def get_scrubber() -> Scrubber:
    global _DEFAULT_SCRUBBER
    if _DEFAULT_SCRUBBER is None:
        _DEFAULT_SCRUBBER = Scrubber()
    return _DEFAULT_SCRUBBER
