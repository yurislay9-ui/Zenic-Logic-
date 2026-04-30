"""
TITAN OMNISCALE X - GitHub Scrap Agent (Pure Python)

Agente de scraping con urllib (sin httpx).
Compatible con Android.
"""
import os
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class GitHubScrapAgent:
    async def fetch_modern_code(self, query, language="kotlin"):
        url = f"https://api.github.com/search/code?q={query}+language:{language}&sort=stars"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TITAN",
        }
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data.get("items"):
                    item = data["items"][0]
                    raw_url = f"https://raw.githubusercontent.com/{item['repository']['full_name']}/main/{item['path']}"
                    raw_req = urllib.request.Request(raw_url, headers=headers)
                    try:
                        with urllib.request.urlopen(raw_req, timeout=10) as raw_resp:
                            return raw_resp.read().decode()[:1500]
                    except Exception:
                        pass
        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.warning("GitHub API rate limit alcanzado. Configura GITHUB_TOKEN.")
        except Exception as e:
            logger.warning("Error al scrapear GitHub: %s", e)
        return ""
