import os
import logging
import httpx

logger = logging.getLogger(__name__)


class GitHubScrapAgent:
    async def fetch_modern_code(self, query: str, language: str = "kotlin") -> str:
        url = f"https://api.github.com/search/code?q={query}+language:{language}&sort=stars"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TITAN",
        }
        # Usar token de GitHub si está disponible para evitar rate-limit
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        async with httpx.AsyncClient(timeout=10.0) as c:
            try:
                r = await c.get(url, headers=headers)
                if r.status_code == 200 and r.json().get("items"):
                    i = r.json()["items"][0]
                    raw = await c.get(
                        f"https://raw.githubusercontent.com/{i['repository']['full_name']}/main/{i['path']}",
                        headers=headers,
                    )
                    return raw.text[:1500] if raw.status_code == 200 else ""
                elif r.status_code == 403:
                    logger.warning("GitHub API rate limit alcanzado. Considera configurar GITHUB_TOKEN.")
            except httpx.HTTPError as e:
                logger.warning("Error HTTP al scrapear GitHub: %s", e)
            except Exception as e:
                logger.warning("Error inesperado al scrapear GitHub: %s", e)
        return ""
