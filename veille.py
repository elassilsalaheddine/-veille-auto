#!/usr/bin/env python3
"""Veille technologique automatique.

Lit les flux RSS/Atom définis dans config.yaml, garde les articles récents
qui contiennent les mots-clés de chaque thème, ignore ceux déjà vus lors des
exécutions précédentes, et écrit un résumé Markdown daté dans digests/.

Usage :
    python veille.py                     # utilise config.yaml
    python veille.py --config autre.yaml
    python veille.py --days 14           # remplace days_back
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import yaml

USER_AGENT = "veille-auto/1.0 (+https://github.com/)"
TIMEOUT = 20
SEEN_FILE = "seen.json"


@dataclass
class Article:
    theme: str
    source: str
    title: str
    link: str
    published: datetime | None
    summary: str
    matched: list[str]


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen(path: Path) -> set[str]:
    if path.exists():
        return set(json.loads(path.read_text(encoding="utf-8")))
    return set()


def save_seen(path: Path, seen: set[str]) -> None:
    # On garde les 5 000 derniers liens pour que le fichier reste petit.
    path.write_text(json.dumps(sorted(seen)[-5000:], ensure_ascii=False, indent=0), encoding="utf-8")


def fetch(url: str) -> feedparser.FeedParserDict:
    """Télécharge un flux (URL http(s) ou chemin local, utile pour les tests)."""
    if url.startswith(("http://", "https://")):
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    else:
        parsed = feedparser.parse(Path(url).read_bytes())
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"flux illisible ({parsed.bozo_exception})")
    return parsed


def entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return None


def clean(text: str, limit: int = 220) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def match_keywords(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    found = []
    for kw in keywords:
        # Limite de mot pour éviter que "RAG" corresponde à "garage".
        if re.search(rf"(?<!\w){re.escape(kw.lower())}(?!\w)", lowered):
            found.append(kw)
    return found


def collect(config: dict, days_back: int, seen: set[str]) -> tuple[list[Article], list[tuple[str, str]]]:
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    articles: list[Article] = []
    errors: list[tuple[str, str]] = []

    for theme_id, theme in config["themes"].items():
        keywords = theme.get("keywords") or []
        for feed in theme.get("feeds", []):
            try:
                parsed = fetch(feed["url"])
            except Exception as exc:  # un flux en panne ne doit pas bloquer les autres
                errors.append((feed["name"], f"{feed['url']} → {exc}"))
                continue

            for entry in parsed.entries:
                link = entry.get("link", "")
                if not link or link in seen:
                    continue
                published = entry_date(entry)
                if published and published < since:
                    continue
                title = clean(entry.get("title", "(sans titre)"), 160)
                summary = clean(entry.get("summary", ""))
                if feed.get("all"):
                    matched = []
                else:
                    matched = match_keywords(f"{title} {summary}", keywords)
                    if not matched:
                        continue
                articles.append(Article(theme_id, feed["name"], title, link, published, summary, matched))
    return articles, errors


def render(config: dict, articles: list[Article], errors: list[tuple[str, str]], days_back: int) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    max_per_theme = config.get("max_per_theme", 15)
    lines = [
        f"# Veille technologique – {today}",
        "",
        f"Articles des {days_back} derniers jours, filtrés par thème. "
        f"{len(articles)} nouvel(s) article(s) trouvé(s).",
        "",
        "> À lire avec la grille d'esprit critique : auteur et source, date, preuves, contexte.",
        "",
    ]

    for theme_id, theme in config["themes"].items():
        items = [a for a in articles if a.theme == theme_id]
        items.sort(key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        lines.append(f"## {theme['title']} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("_Rien de nouveau cette semaine._")
            lines.append("")
            continue
        for a in items[:max_per_theme]:
            date = a.published.strftime("%d/%m/%Y") if a.published else "date inconnue"
            tags = f" · mots-clés : {', '.join(a.matched)}" if a.matched else ""
            lines.append(f"- **[{a.title}]({a.link})** – {a.source}, {date}{tags}")
            if a.summary:
                lines.append(f"  {a.summary}")
        if len(items) > max_per_theme:
            lines.append(f"- … et {len(items) - max_per_theme} autre(s) non affiché(s).")
        lines.append("")

    if errors:
        lines.append("## Flux en erreur")
        lines.append("")
        lines.append("Ces flux n'ont pas pu être lus : vérifiez leur URL dans config.yaml.")
        lines.append("")
        for name, detail in errors:
            lines.append(f"- {name} : `{detail}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Veille technologique automatique")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--days", type=int, help="nombre de jours à couvrir")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    days_back = args.days or config.get("days_back", 7)

    base = config_path.parent
    out_dir = base / config.get("output_dir", "digests")
    out_dir.mkdir(parents=True, exist_ok=True)
    seen_path = base / SEEN_FILE
    seen = load_seen(seen_path)

    articles, errors = collect(config, days_back, seen)
    report = render(config, articles, errors, days_back)

    out_file = out_dir / f"{datetime.now(timezone.utc).date().isoformat()}.md"
    out_file.write_text(report, encoding="utf-8")
    (out_dir / "latest.md").write_text(report, encoding="utf-8")

    seen.update(a.link for a in articles)
    save_seen(seen_path, seen)

    print(f"{len(articles)} article(s), {len(errors)} flux en erreur → {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
