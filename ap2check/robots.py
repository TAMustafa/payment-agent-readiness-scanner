"""robots.txt parser following RFC 9309 (https://www.rfc-editor.org/rfc/rfc9309).

Own implementation instead of urllib.robotparser, which does not support `*` / `$`
wildcards or longest-match precedence (RFC 9309 §2.2.2), both of which real shops use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

from ap2check.models import FetchedResource

# Max bytes parsed, per RFC 9309 §2.5 (at least 500 KiB must be parsed).
MAX_ROBOTS_BYTES = 500 * 1024


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str
    line_no: int

    def text(self) -> str:
        return f"{'Allow' if self.allow else 'Disallow'}: {self.pattern}"

    def matches(self, path: str) -> bool:
        return _compile(self.pattern).match(path) is not None


@dataclass
class Group:
    agents: list[str]  # lower-cased product tokens
    rules: list[Rule] = field(default_factory=list)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    group: str  # "token" | "*" | "none" | "policy"
    rule: Rule | None


@dataclass
class RobotsTxt:
    groups: list[Group] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    policy: str | None = None  # "allow_all" / "disallow_all" when not parsed from a file

    @classmethod
    def allow_all(cls) -> RobotsTxt:
        return cls(policy="allow_all")

    @classmethod
    def disallow_all(cls) -> RobotsTxt:
        return cls(policy="disallow_all")

    @classmethod
    def parse(cls, text: str) -> RobotsTxt:
        robots = cls()
        current: Group | None = None
        last_was_agent = False
        for line_no, raw in enumerate(text[:MAX_ROBOTS_BYTES].splitlines(), start=1):
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (p.strip() for p in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = Group(agents=[])
                    robots.groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if key in ("allow", "disallow"):
                if current is None or not value:
                    continue  # rules outside a group, or empty pattern (= no rule)
                current.rules.append(Rule(key == "allow", value, line_no))
            elif key == "sitemap" and value:
                robots.sitemaps.append(value)
        return robots

    def decide(self, token: str, url_or_path: str) -> Decision:
        if self.policy == "allow_all":
            return Decision(True, "policy", None)
        if self.policy == "disallow_all":
            return Decision(False, "policy", None)
        path = _path_of(url_or_path)
        if path == "/robots.txt":
            return Decision(True, "none", None)  # RFC 9309 §2.2.2: always allowed

        tok = token.lower()
        matched = [g for g in self.groups if tok in g.agents]
        group_label = "token"
        if not matched:
            matched = [g for g in self.groups if "*" in g.agents]
            group_label = "*"
        if not matched:
            return Decision(True, "none", None)

        best: Rule | None = None
        for rule in (r for g in matched for r in g.rules):
            if not rule.matches(path):
                continue
            if (
                best is None
                or len(rule.pattern) > len(best.pattern)
                or (len(rule.pattern) == len(best.pattern) and rule.allow and not best.allow)
            ):
                best = rule
        return Decision(best is None or best.allow, group_label, best)

    def is_allowed(self, token: str, url_or_path: str) -> bool:
        return self.decide(token, url_or_path).allowed


def robots_from_resource(res: FetchedResource | None) -> RobotsTxt | None:
    """Apply RFC 9309 §2.3.1 status handling. None = could not determine (network error)."""
    if res is None or res.status_code is None:
        return None
    if 200 <= res.status_code < 300:
        return RobotsTxt.parse(res.body or "")
    if 400 <= res.status_code < 500:
        return RobotsTxt.allow_all()  # "unavailable": crawlers may access everything
    return RobotsTxt.disallow_all()  # 5xx = "unreachable": assume complete disallow


def _path_of(url_or_path: str) -> str:
    if url_or_path.startswith("/"):
        path = url_or_path
    else:
        parts = urlsplit(url_or_path)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return unquote(path)


_cache: dict[str, re.Pattern[str]] = {}


def _compile(pattern: str) -> re.Pattern[str]:
    rx = _cache.get(pattern)
    if rx is None:
        pat = unquote(pattern)
        anchored = pat.endswith("$")
        if anchored:
            pat = pat[:-1]
        body = ".*".join(re.escape(part) for part in pat.split("*"))
        rx = re.compile(body + ("$" if anchored else ""))
        _cache[pattern] = rx
    return rx
