"""
TITAN OMNISCALE X - Smart Scraper Agent v16 (Pure Python)

Scraper Inteligente multi-fuente con urllib (sin httpx, sin requests).
Compatible con Android/Termux, zero dependencias externas.

Fuentes integradas:
1. GitHub Code Search    - Busca codigo real en repos publicos (con API key)
2. DevDocs               - Documentacion de lenguajes y APIs (0 registro)
3. IconStack             - Iconos para UIs generadas (0 registro)
4. Picsum.photos         - Imagenes aleatorias profesionales (0 registro)

Configuracion via .env (ver .env.example):
- GITHUB_TOKEN / GITHUB_API_KEY: Token de GitHub (5000 req/h vs 60 req/h)
- GITHUB_METRICS_ENABLED: Recopilar metricas de GitHub
- SCRAPER_PREFERRED_SOURCE: github | devdocs | iconstack | picsum | auto
- SCRAPER_TIMEOUT: Timeout global en segundos
- SCRAPER_MAX_CHARS: Maximo de caracteres por fuente

Arquitectura:
- smart_fetch(): Auto-selecciona la fuente segun tipo de consulta
- fetch_modern_code(): Backward-compatible con el pipeline original
- Cada fuente tiene su propio metodo fetch_xxx() independiente
- Todas las fuentes usan urllib puro (stdlib), sin dependencias
- Metricas de GitHub integradas (rate_limit, search_stats)
"""

import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any

from src.core.env_loader import (
    load_env, get_env, get_env_int, get_env_bool,
    get_env_list, get_github_token, get_scraper_config,
)

logger = logging.getLogger(__name__)


# ============================================================
#  GITHUB METRICS - Recopilacion de metricas de la API
# ============================================================

class GitHubMetrics:
    """
    Recopila metricas de uso de la API de GitHub.

    Metricas disponibles:
    - rate_limit: Requests restantes y reset time
    - search_results: Conteo de resultados por query
    - repo_stats: Estadisticas de repos encontrados
    """

    def __init__(self):
        self.enabled = get_env_bool("GITHUB_METRICS_ENABLED", True)
        self.collect = get_env_list(
            "GITHUB_METRICS_COLLECT",
            ["rate_limit", "search_results", "repo_stats"]
        )
        self.refresh_interval = get_env_int("GITHUB_METRICS_REFRESH_INTERVAL", 300)

        # Estado interno
        self._rate_limit_remaining = 0
        self._rate_limit_limit = 0
        self._rate_limit_reset = 0
        self._rate_limit_last_check = 0
        self._search_count = 0
        self._search_results_total = 0
        self._repos_seen: set = set()
        self._repos_seen_max = 10000
        self._last_refresh = 0.0

    def update_rate_limit(self, response_headers: dict):
        """Actualiza metricas de rate limit desde headers de respuesta GitHub."""
        if not self.enabled or "rate_limit" not in self.collect:
            return

        try:
            self._rate_limit_remaining = int(
                response_headers.get("X-RateLimit-Remaining", "0")
            )
        except (ValueError, TypeError):
            self._rate_limit_remaining = 0
        try:
            self._rate_limit_limit = int(
                response_headers.get("X-RateLimit-Limit", "0")
            )
        except (ValueError, TypeError):
            self._rate_limit_limit = 0
        try:
            self._rate_limit_reset = int(
                response_headers.get("X-RateLimit-Reset", "0")
            )
        except (ValueError, TypeError):
            self._rate_limit_reset = 0
        self._rate_limit_last_check = time.time()

    def update_search_stats(self, total_count: int, query: str):
        """Actualiza estadisticas de busqueda."""
        if not self.enabled or "search_results" not in self.collect:
            return
        self._search_count += 1
        self._search_results_total += total_count

    def update_repo_stats(self, repo_full_name: str, stars: int = 0):
        """Actualiza estadisticas de repositorios."""
        if not self.enabled or "repo_stats" not in self.collect:
            return
        self._repos_seen.add(repo_full_name)
        if len(self._repos_seen) > self._repos_seen_max:
            # Clear half to prevent unbounded growth
            remove = list(self._repos_seen)[:len(self._repos_seen) // 2]
            for item in remove:
                self._repos_seen.discard(item)

    async def fetch_rate_limit(self, token: str = "") -> Dict[str, Any]:
        """
        Obtiene el estado actual del rate limit de GitHub API.
        Requiere token para el endpoint /rate_limit.
        """
        if not token:
            token = get_github_token()
        if not token:
            return {"error": "No GITHUB_TOKEN configured"}

        url = "https://api.github.com/rate_limit"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TITAN-SmartScraper",
            "Authorization": f"token {token}",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                resources = data.get("resources", {})
                search = resources.get("search", {})
                core = resources.get("core", {})

                self._rate_limit_remaining = core.get("remaining", 0)
                self._rate_limit_limit = core.get("limit", 0)
                self._rate_limit_reset = core.get("reset", 0)
                self._rate_limit_last_check = time.time()

                return {
                    "core": {
                        "remaining": core.get("remaining", 0),
                        "limit": core.get("limit", 0),
                        "reset": core.get("reset", 0),
                    },
                    "search": {
                        "remaining": search.get("remaining", 0),
                        "limit": search.get("limit", 0),
                        "reset": search.get("reset", 0),
                    },
                }
        except Exception as e:
            logger.debug("GitHubMetrics: Failed to fetch rate_limit: %s", e)
            return {"error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """Retorna todas las metricas recopiladas."""
        stats = {}
        if "rate_limit" in self.collect:
            stats["rate_limit"] = {
                "remaining": self._rate_limit_remaining,
                "limit": self._rate_limit_limit,
                "reset_timestamp": self._rate_limit_reset,
                "last_check": self._rate_limit_last_check,
            }
        if "search_results" in self.collect:
            stats["search"] = {
                "queries_made": self._search_count,
                "total_results": self._search_results_total,
            }
        if "repo_stats" in self.collect:
            stats["repos"] = {
                "unique_repos_seen": len(self._repos_seen),
                "repo_names": list(self._repos_seen)[:20],  # Ultimos 20
            }
        return stats


# ============================================================
#  SMART SCRAPER - Orquestador multi-fuente
# ============================================================

class GitHubScrapAgent:
    """
    Smart Scraper Agent v16 - Multi-fuente, auto-routing.

    Mantiene backward compatibility con fetch_modern_code() del
    pipeline original, pero anade smart_fetch() para seleccion
    automatica de fuente y metodos individuales por fuente.

    Fuentes:
    - github:   Busca codigo en repos publicos (con GITHUB_TOKEN)
    - devdocs:  Documentacion de lenguajes y APIs (0 registro)
    - iconstack: Iconos para UIs (0 registro)
    - picsum:   Imagenes aleatorias profesionales (0 registro)

    Uso basico (backward-compatible):
        scraper = GitHubScrapAgent()
        code = await scraper.fetch_modern_code("auth login", "python")

    Uso avanzado (auto-routing):
        result = await scraper.smart_fetch("how to use asyncio", "python")
        # Auto-selecciona: devdocs (documentacion)

        result = await scraper.smart_fetch("kotlin coroutines example", "kotlin")
        # Auto-selecciona: github (codigo de ejemplo)

        result = await scraper.smart_fetch("material icon for login button", "")
        # Auto-selecciona: iconstack (iconos)

        result = await scraper.smart_fetch("hero image for dashboard", "")
        # Auto-selecciona: picsum (imagen aleatoria)
    """

    # Keywords que indican tipo de consulta para auto-routing
    CODE_KEYWORDS = {
        "example", "implement", "code", "function", "class", "module",
        "snippet", "how to", "create a", "build a", "pattern", "algorithm",
        "repository", "repo", "github", "library", "package", "import",
        "ejemplo", "implementar", "funcion", "clase", "modulo", "patron",
    }

    DOCS_KEYWORDS = {
        "docs", "documentation", "reference", "api", "syntax", "method",
        "parameter", "return", "type", "class reference", "how does",
        "what is", "explain", "tutorial", "guide", "specification",
        "documentacion", "referencia", "sintaxis", "metodo", "explicar",
        "guia", "tutorial",
    }

    ICON_KEYWORDS = {
        "icon", "icons", "svg", "symbol", "logo", "badge", "avatar",
        "button icon", "menu icon", "navigation icon", "tab icon",
        "icono", "iconos", "simbolo", "logo", "insignia",
    }

    IMAGE_KEYWORDS = {
        "image", "photo", "picture", "hero", "banner", "background",
        "cover", "thumbnail", "placeholder", "avatar image", "header",
        "imagen", "foto", "imagen de fondo", "portada", "miniatura",
        "placeholder image", "hero image",
    }

    def __init__(self):
        """Inicializa el Smart Scraper con config desde .env."""
        # Cargar .env si no se ha hecho
        load_env()

        # Configuracion del scraper
        self._config = get_scraper_config()
        self._timeout = self._config["timeout"]
        self._max_retries = self._config["max_retries"]
        self._max_chars = self._config["max_chars"]
        self._preferred_source = self._config["preferred_source"]

        # Metricas de GitHub
        self._metrics = GitHubMetrics()

        # Cache de resultados simples (evita fetch duplicado en misma sesion)
        self._cache: Dict[str, str] = {}

        logger.info(
            "SmartScraper v16: sources=[github,devdocs,iconstack,picsum] "
            "preferred=%s timeout=%ds max_chars=%d token=%s",
            self._preferred_source, self._timeout, self._max_chars,
            "YES" if self._config["github_token"] else "NO"
        )

    @property
    def metrics(self) -> GitHubMetrics:
        """Acceso a las metricas de GitHub."""
        return self._metrics

    @property
    def config(self) -> dict:
        """Acceso a la configuracion del scraper."""
        return self._config

    # ============================================================
    #  BACKWARD COMPATIBILITY - fetch_modern_code()
    # ============================================================

    async def fetch_modern_code(self, query, language="kotlin"):
        """
        Backward-compatible: Busca codigo en GitHub.

        Este es el metodo original del pipeline (SCRAPE_PATTERNS).
        Se mantiene para compatibilidad con DAGOrchestrator y
        TitanOrchestrator existentes.

        Args:
            query: Termino de busqueda
            language: Lenguaje de programacion (default: kotlin)

        Returns:
            str: Codigo encontrado (hasta max_chars), o "" si falla
        """
        return await self.fetch_github_code(query, language)

    # ============================================================
    #  AUTO-ROUTING - smart_fetch()
    # ============================================================

    async def smart_fetch(self, query: str, language: str = "",
                          source: str = "") -> Dict[str, Any]:
        """
        Auto-routing: Selecciona la fuente optima segun el tipo de consulta.

        Si source es "auto" (default), analiza keywords en la query para
        determinar la fuente. Si se especifica una fuente, la usa directamente.

        Args:
            query: Termino de busqueda o consulta
            language: Lenguaje de programacion (opcional)
            source: Fuente forzada: github|devdocs|iconstack|picsum|auto

        Returns:
            dict con: source, content, metadata, success
        """
        # Determinar fuente
        if not source or source == "auto":
            source = self._preferred_source
            if source == "auto":
                source = self._detect_source(query)

        # Check cache
        cache_key = f"{source}:{query}:{language}"
        if cache_key in self._cache:
            logger.debug("SmartScraper: Cache hit for %s", cache_key[:60])
            return {
                "source": source,
                "content": self._cache[cache_key],
                "metadata": {"cached": True},
                "success": True,
            }

        # Dispatch a la fuente seleccionada
        result = {"source": source, "content": "", "metadata": {}, "success": False}

        if source == "github":
            content = await self.fetch_github_code(query, language)
            result["content"] = content
            result["success"] = bool(content)

        elif source == "devdocs":
            content = await self.fetch_devdocs(query, language)
            result["content"] = content
            result["success"] = bool(content)

        elif source == "iconstack":
            content = await self.fetch_iconstack(query)
            result["content"] = content
            result["success"] = bool(content)

        elif source == "picsum":
            content = await self.fetch_picsum(query)
            result["content"] = content
            result["success"] = bool(content)

        else:
            logger.warning("SmartScraper: Unknown source '%s', falling back to github", source)
            content = await self.fetch_github_code(query, language)
            result["source"] = "github"
            result["content"] = content
            result["success"] = bool(content)

        # Cache resultado exitoso
        if result["success"] and result["content"]:
            self._cache[cache_key] = result["content"]
            # Limitar tamano del cache (max 100 entradas)
            if len(self._cache) > 100:
                # Eliminar entradas mas antiguas (FIFO simplificado)
                keys = list(self._cache.keys())
                to_evict = max(20, len(self._cache) - 90)
                for k in keys[:to_evict]:
                    del self._cache[k]

        return result

    def _detect_source(self, query: str) -> str:
        """
        Detecta la fuente optima basandose en keywords de la query.

        Prioridad: iconstack > picsum > devdocs > github
        (las fuentes mas especificas tienen prioridad)
        """
        query_lower = query.lower()

        # Check iconos primero (muy especifico)
        icon_score = sum(1 for kw in self.ICON_KEYWORDS if kw in query_lower)
        if icon_score >= 1:
            return "iconstack"

        # Check imagenes
        image_score = sum(1 for kw in self.IMAGE_KEYWORDS if kw in query_lower)
        if image_score >= 1:
            return "picsum"

        # Check documentacion
        docs_score = sum(1 for kw in self.DOCS_KEYWORDS if kw in query_lower)
        if docs_score >= 2:
            return "devdocs"

        # Check codigo
        code_score = sum(1 for kw in self.CODE_KEYWORDS if kw in query_lower)
        if code_score >= 1:
            return "github"

        # Default: github (fuente mas versatil para codigo)
        return "github"

    # ============================================================
    #  FUENTE 1: GITHUB - Busqueda de codigo con API key
    # ============================================================

    async def fetch_github_code(self, query: str, language: str = "python") -> str:
        """
        Busca codigo en repositorios publicos de GitHub.

        Usa GITHUB_TOKEN del .env para autenticacion.
        Sin token: 60 requests/hora | Con token: 5000 requests/hora.

        Args:
            query: Termino de busqueda
            language: Lenguaje de programacion

        Returns:
            str: Codigo encontrado (hasta max_chars), o "" si falla
        """
        # Obtener token desde .env
        github_token = self._config["github_token"]

        encoded_query = urllib.parse.quote(query, safe='')
        lang_param = f"+language:{language}" if language else ""
        url = (
            f"https://api.github.com/search/code?"
            f"q={encoded_query}{lang_param}&sort=stars&per_page=5"
        )

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TITAN-SmartScraper",
        }

        # Usar token si esta disponible (5000 req/h vs 60 req/h)
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        # Reintentos con backoff
        for attempt in range(self._max_retries + 1):
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    # Actualizar metricas de rate limit
                    resp_headers = dict(resp.headers)
                    self._metrics.update_rate_limit(resp_headers)

                    data = json.loads(resp.read().decode())

                    # Metricas de busqueda
                    total_count = data.get("total_count", 0)
                    self._metrics.update_search_stats(total_count, query)

                    if not data.get("items"):
                        logger.debug(
                            "GitHub: No results for '%s' (lang=%s, total=%d)",
                            query[:50], language, total_count
                        )
                        return ""

                    # Probar cada resultado hasta encontrar codigo valido
                    for item in data["items"][:3]:
                        repo_name = item.get("repository", {}).get("full_name", "")
                        file_path = item.get("path", "")

                        # Metricas de repo
                        self._metrics.update_repo_stats(repo_name)

                        # Construir URL al archivo raw
                        # Probar main primero, luego master
                        for branch in ("main", "master"):
                            raw_url = (
                                f"https://raw.githubusercontent.com/"
                                f"{repo_name}/{branch}/{file_path}"
                            )
                            raw_req = urllib.request.Request(
                                raw_url, headers=headers
                            )
                            try:
                                with urllib.request.urlopen(
                                    raw_req, timeout=self._timeout
                                ) as raw_resp:
                                    code = raw_resp.read().decode()
                                    if code.strip():
                                        logger.info(
                                            "GitHub: Found code from %s/%s "
                                            "(%d chars, branch=%s)",
                                            repo_name, file_path,
                                            len(code), branch
                                        )
                                        return code[:self._max_chars]
                            except Exception:
                                continue

                    logger.debug("GitHub: Found items but no raw code accessible")
                    return ""

            except urllib.error.HTTPError as e:
                if e.code == 403:
                    # Rate limit alcanzado
                    reset_time = e.headers.get("X-RateLimit-Reset", "0")
                    remaining = e.headers.get("X-RateLimit-Remaining", "0")
                    logger.warning(
                        "GitHub API rate limit (remaining=%s, reset=%s). "
                        "Configura GITHUB_TOKEN en .env para 5000 req/h.",
                        remaining, reset_time
                    )
                    # No reintentar si es rate limit
                    return ""
                elif e.code == 422:
                    logger.debug("GitHub: Invalid query '%s'", query[:50])
                    return ""
                elif e.code >= 500:
                    # Error del servidor, reintentar
                    if attempt < self._max_retries:
                        wait = (attempt + 1) * 2
                        logger.debug(
                            "GitHub: Server error %d, retrying in %ds",
                            e.code, wait
                        )
                        time.sleep(wait)
                        continue
                else:
                    logger.debug("GitHub: HTTP %d for '%s'", e.code, query[:50])
                    return ""

            except urllib.error.URLError as e:
                if attempt < self._max_retries:
                    wait = (attempt + 1) * 2
                    logger.debug(
                        "GitHub: URL error %s, retrying in %ds",
                        str(e.reason)[:50], wait
                    )
                    time.sleep(wait)
                    continue
                logger.warning("GitHub: URL error: %s", e.reason)

            except Exception as e:
                logger.warning("GitHub: Error fetching '%s': %s", query[:50], e)
                return ""

        return ""

    # ============================================================
    #  FUENTE 2: DEVDOCS - Documentacion de lenguajes (0 registro)
    # ============================================================

    async def fetch_devdocs(self, query: str, language: str = "") -> str:
        """
        Busca documentacion en DevDocs (https://devdocs.io).

        DevDocs es 100% gratuito, sin registro y sin API key.
        Agrega documentacion de Python, JavaScript, TypeScript,
        HTML, CSS, Kotlin, y decenas de lenguajes mas.

        La API de DevDocs permite buscar y obtener documentacion
        directamente: https://devdocs.io/docs/{doc}/index.json
        y buscar: https://devdocs.io/docs/{doc}/search.json?q={query}

        Args:
            query: Termino de busqueda (ej: "asyncio.gather", "Array.map")
            language: Lenguaje para acotar la busqueda

        Returns:
            str: Documentacion encontrada, o "" si falla
        """
        # Mapear lenguaje a documento DevDocs
        lang_to_doc = {
            "python": "python~3.12",
            "python3": "python~3.12",
            "kotlin": "kotlin",
            "javascript": "javascript",
            "js": "javascript",
            "typescript": "typescript",
            "ts": "typescript",
            "html": "html",
            "css": "css",
            "react": "react",
            "node": "node",
            "nodejs": "node",
            "go": "go",
            "rust": "rust",
            "java": "java",
            "ruby": "ruby",
            "php": "php",
            "c": "c",
            "cpp": "cpp",
            "csharp": "csharp",
            "swift": "swift",
            "dart": "dart",
            "flutter": "flutter",
        }

        doc_name = lang_to_doc.get(language.lower(), "") if language else ""

        # Si no tenemos doc para el lenguaje, probar con Python como default
        if not doc_name and language:
            doc_name = lang_to_doc.get(language.lower(), "python~3.12")

        # Estrategia 1: Buscar en un documento especifico
        if doc_name:
            result = await self._devdocs_search(doc_name, query)
            if result:
                return result

        # Estrategia 2: Buscar en documentos populares si no se especifico lenguaje
        popular_docs = ["python~3.12", "javascript", "typescript", "html", "css", "kotlin"]
        for doc in popular_docs[:3]:  # Solo probar los 3 mas relevantes
            if doc == doc_name:
                continue  # Ya lo probamos
            result = await self._devdocs_search(doc, query)
            if result:
                return result

        return ""

    async def _devdocs_search(self, doc_name: str, query: str) -> str:
        """
        Busca en un documento especifico de DevDocs.

        Usa la API de busqueda: /docs/{doc}/search.json?q={query}
        y la API de entradas: /docs/{doc}/index.json
        """
        base_url = self._config.get("devdocs_url", "https://devdocs.io")

        # Primero buscar entradas relevantes
        search_url = f"{base_url}/docs/{doc_name}/search.json?q={urllib.parse.quote(query, safe='')}"
        headers = {
            "User-Agent": "TITAN-SmartScraper",
            "Accept": "application/json",
        }

        try:
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode())

                if not data:
                    return ""

                # DevDocs search.json retorna una lista de [name, path, signature?]
                # Formato: [["name", "path", "signature"], ...]
                results = []
                for entry in data[:5]:
                    if isinstance(entry, list) and len(entry) >= 2:
                        name = entry[0]
                        path = entry[1]
                        sig = entry[2] if len(entry) > 2 else ""
                        results.append(f"**{name}**\n  Path: {path}\n  Signature: {sig}")
                    elif isinstance(entry, dict):
                        name = entry.get("name", "")
                        path = entry.get("path", "")
                        sig = entry.get("signature", entry.get("doc", ""))
                        results.append(f"**{name}**\n  Path: {path}\n  Signature: {sig}")

                if results:
                    doc_text = (
                        f"[DevDocs: {doc_name}]\n\n"
                        + "\n\n".join(results)
                    )
                    logger.info(
                        "DevDocs: Found %d results for '%s' in %s",
                        len(results), query[:30], doc_name
                    )
                    return doc_text[:self._max_chars]

        except urllib.error.HTTPError as e:
            logger.debug("DevDocs: HTTP %d for %s search", e.code, doc_name)
        except Exception as e:
            logger.debug("DevDocs: Error searching %s: %s", doc_name, str(e)[:80])

        return ""

    # ============================================================
    #  FUENTE 3: ICONSTACK - Iconos para UIs (0 registro)
    # ============================================================

    async def fetch_iconstack(self, query: str) -> str:
        """
        Busca iconos en IconStack (https://icon-icons.com).

        IconStack es 100% gratuito, sin registro y sin API key.
        Provee miles de iconos en multiples estilos (Material,
        FontAwesome, etc.) para apps y frontends generados.

        Retorna URLs de iconos que el motor puede usar para
        inyectar en frontends generados automaticamente.

        Args:
            query: Nombre del icono (ej: "login", "menu", "settings")

        Returns:
            str: JSON con URLs de iconos, o "" si falla
        """
        base_url = self._config.get("iconstack_url", "https://icon-icons.com")
        style = self._config.get("iconstack_style", "material")

        # IconStack search URL
        search_url = (
            f"{base_url}/api/search?"
            f"q={urllib.parse.quote(query, safe='')}"
            f"&style={style}"
        )

        headers = {
            "User-Agent": "TITAN-SmartScraper",
            "Accept": "application/json, text/html",
        }

        try:
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")

                # Si retorna JSON (API)
                if "json" in content_type:
                    data = json.loads(resp.read().decode())
                    icons = data if isinstance(data, list) else data.get("icons", [])
                    results = []
                    for icon in icons[:5]:
                        name = icon.get("name", "")
                        svg_url = icon.get("svg_url", icon.get("url", ""))
                        png_url = icon.get("png_url", "")
                        results.append({
                            "name": name,
                            "svg_url": svg_url,
                            "png_url": png_url,
                            "style": style,
                        })
                    if results:
                        output = json.dumps({
                            "source": "iconstack",
                            "query": query,
                            "icons": results,
                        }, ensure_ascii=False, indent=2)
                        logger.info(
                            "IconStack: Found %d icons for '%s'",
                            len(results), query[:30]
                        )
                        return output[:self._max_chars]

                # Si retorna HTML, extraer URLs de iconos con parseo simple
                elif "html" in content_type:
                    html = resp.read().decode()
                    # Buscar URLs de iconos en el HTML
                    icon_urls = self._extract_icon_urls(html, query)
                    if icon_urls:
                        output = json.dumps({
                            "source": "iconstack",
                            "query": query,
                            "icons": icon_urls[:5],
                        }, ensure_ascii=False, indent=2)
                        logger.info(
                            "IconStack: Found %d icons for '%s' (HTML parse)",
                            len(icon_urls), query[:30]
                        )
                        return output[:self._max_chars]

        except urllib.error.HTTPError as e:
            logger.debug("IconStack: HTTP %d for '%s'", e.code, query[:30])
        except Exception as e:
            logger.debug("IconStack: Error: %s", str(e)[:80])

        # Fallback: Generar URLs de iconos conocidos (Material Design)
        # Estos son URLs directos que siempre funcionan
        material_icons = {
            "login": "https://icon-icons.com/icons2/2099/PNG/512/login_enter_icon_128544.png",
            "logout": "https://icon-icons.com/icons2/2099/PNG/512/logout_icon_128543.png",
            "menu": "https://icon-icons.com/icons2/2099/PNG/512/menu_hamburger_icon_128549.png",
            "settings": "https://icon-icons.com/icons2/2099/PNG/512/settings_gear_icon_128533.png",
            "home": "https://icon-icons.com/icons2/2099/PNG/512/home_house_icon_128540.png",
            "user": "https://icon-icons.com/icons2/2099/PNG/512/user_person_icon_128546.png",
            "search": "https://icon-icons.com/icons2/2099/PNG/512/search_magnifier_icon_128542.png",
            "add": "https://icon-icons.com/icons2/2099/PNG/512/plus_add_icon_128536.png",
            "delete": "https://icon-icons.com/icons2/2099/PNG/512/trash_delete_icon_128538.png",
            "edit": "https://icon-icons.com/icons2/2099/PNG/512/edit_pencil_icon_128539.png",
            "save": "https://icon-icons.com/icons2/2099/PNG/512/floppy_save_icon_128541.png",
            "dashboard": "https://icon-icons.com/icons2/2099/PNG/512/dashboard_icon_128545.png",
            "notification": "https://icon-icons.com/icons2/2099/PNG/512/bell_notification_icon_128547.png",
            "email": "https://icon-icons.com/icons2/2099/PNG/512/email_mail_icon_128548.png",
            "lock": "https://icon-icons.com/icons2/2099/PNG/512/lock_security_icon_128534.png",
        }

        query_lower = query.lower().strip()
        # Buscar match directo o parcial
        matched = None
        for key, url in material_icons.items():
            if key == query_lower or key in query_lower or query_lower in key:
                matched = {"name": key, "png_url": url, "style": "material"}
                break

        if matched:
            output = json.dumps({
                "source": "iconstack",
                "query": query,
                "icons": [matched],
                "note": "Fallback Material Design icon (offline)",
            }, ensure_ascii=False, indent=2)
            logger.info("IconStack: Found fallback icon for '%s'", query[:30])
            return output[:self._max_chars]

        logger.debug("IconStack: No icons found for '%s'", query[:30])
        return ""

    def _extract_icon_urls(self, html: str, query: str) -> list:
        """
        Extrae URLs de iconos de HTML de IconStack.
        Busca patrones como href="..." y src="..." con extensiones de imagen.
        """
        icons = []
        # Buscar URLs de imagenes PNG/SVG en el HTML
        import re
        img_pattern = re.compile(
            r'(?:src|href)=["\']([^"\']*icon[^"\']*\.(?:png|svg|jpg))["\']',
            re.IGNORECASE
        )
        for match in img_pattern.findall(html)[:5]:
            url = match
            if not url.startswith("http"):
                url = f"{self._config.get('iconstack_url', 'https://icon-icons.com')}{url}"
            name = url.split("/")[-1].replace(".png", "").replace("_", " ")
            icons.append({"name": name, "url": url, "style": "parsed"})
        return icons

    # ============================================================
    #  FUENTE 4: PICSUM PHOTOS - Imagenes profesionales (0 registro)
    # ============================================================

    async def fetch_picsum(self, query: str = "") -> str:
        """
        Obtiene imagenes aleatorias profesionales de Picsum.photos.

        Picsum.photos es 100% gratuito, sin API key y sin registro.
        Ideal para generar prototipos de frontend con imagenes
        profesionales al instante.

        Ejemplo de uso en el motor:
            https://picsum.photos/800/600  -> Imagen aleatoria 800x600
            https://picsum.photos/id/237/800/600 -> Imagen especifica

        Args:
            query: Descripcion opcional (se ignora, Picsum es aleatorio)
                   Pero se puede usar para dimensiones: "1200x800"

        Returns:
            str: JSON con URL de la imagen y metadata, o "" si falla
        """
        base_url = self._config.get("picsum_url", "https://picsum.photos")
        default_w = self._config.get("picsum_width", 800)
        default_h = self._config.get("picsum_height", 600)

        # Parsear dimensiones de la query si vienen en formato "WxH" o "WxH id=N"
        width, height = default_w, default_h
        image_id = None

        if query:
            # Intentar parsear "1200x800" o "1200x800 id=237"
            import re
            dim_match = re.match(r'(\d+)\s*[xX×]\s*(\d+)', query.strip())
            if dim_match:
                width = int(dim_match.group(1))
                height = int(dim_match.group(2))
                # Limitar dimensiones para no pedir imagenes enormes
                width = min(width, 1920)
                height = min(height, 1080)

            # Intentar parsear "id=237"
            id_match = re.search(r'id\s*=\s*(\d+)', query)
            if id_match:
                image_id = int(id_match.group(1))

        # Construir URL de Picsum
        if image_id:
            image_url = f"{base_url}/id/{image_id}/{width}/{height}"
            info_url = f"{base_url}/id/{image_id}/info"
        else:
            image_url = f"{base_url}/{width}/{height}"
            info_url = ""

        # Intentar obtener metadata de la imagen
        metadata = {"width": width, "height": height}
        if info_url:
            headers = {"User-Agent": "TITAN-SmartScraper"}
            try:
                req = urllib.request.Request(info_url, headers=headers)
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    data = json.loads(resp.read().decode())
                    metadata["author"] = data.get("author", "")
                    metadata["author_url"] = data.get("author_url", "")
                    metadata["original_url"] = data.get("url", "")
                    metadata["image_id"] = data.get("id", image_id)
            except Exception:
                pass  # Metadata es opcional

        # Verificar que la URL de imagen funciona (HEAD request)
        headers = {"User-Agent": "TITAN-SmartScraper"}
        try:
            req = urllib.request.Request(image_url, headers=headers, method="HEAD")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                actual_url = resp.url  # URL final (con redirect de Picsum)
                content_type = resp.headers.get("Content-Type", "")
                content_length = resp.headers.get("Content-Length", "0")

                if "image" in content_type:
                    metadata["actual_url"] = actual_url
                    metadata["content_type"] = content_type
                    try:
                        metadata["size_bytes"] = int(content_length)
                    except (ValueError, TypeError):
                        metadata["size_bytes"] = 0

        except Exception as e:
            # Incluso si falla el HEAD, la URL probablemente funciona
            logger.debug("Picsum: HEAD check failed, using URL as-is: %s", str(e)[:50])
            metadata["actual_url"] = image_url

        output = json.dumps({
            "source": "picsum",
            "image_url": metadata.get("actual_url", image_url),
            "direct_url": image_url,
            "metadata": metadata,
            "usage": {
                "html": f'<img src="{image_url}" alt="placeholder" width="{width}" height="{height}">',
                "css": f"background-image: url('{image_url}');",
                "markdown": f"![placeholder]({image_url})",
                "react": f'<img src="{{"{image_url}"}}" alt="placeholder" />',
            },
        }, ensure_ascii=False, indent=2)

        logger.info(
            "Picsum: Generated image URL %dx%d (id=%s)",
            width, height, image_id or "random"
        )
        return output[:self._max_chars]

    # ============================================================
    #  MULTI-SOURCE FETCH - Busca en todas las fuentes
    # ============================================================

    async def fetch_all_sources(self, query: str,
                                 language: str = "") -> Dict[str, Any]:
        """
        Busca en TODAS las fuentes disponibles y retorna resultados combinados.

        Util cuando se quiere maximizar la informacion obtenida,
        por ejemplo para el nodo SCRAPE_PATTERNS del DAG.

        Fuentes consultadas (en orden):
        1. GitHub  - Codigo de repos publicos (con GITHUB_TOKEN)
        2. DevDocs - Documentacion de lenguajes y APIs (0 registro)
        3. IconStack - Iconos para UIs generadas (0 registro)
        4. Picsum  - Imagenes profesionales aleatorias (0 registro)

        Args:
            query: Termino de busqueda
            language: Lenguaje de programacion

        Returns:
            dict con resultados por fuente: {source: content, ...}
        """
        results = {}
        sources_tried = []

        # 1. GitHub (siempre, es la fuente principal de codigo)
        try:
            github_code = await self.fetch_github_code(query, language)
            if github_code:
                results["github"] = github_code
        except Exception as e:
            logger.debug("fetch_all_sources: GitHub failed: %s", str(e)[:60])
        sources_tried.append("github")

        # 2. DevDocs (documentacion de lenguajes y APIs)
        try:
            devdocs_content = await self.fetch_devdocs(query, language)
            if devdocs_content:
                results["devdocs"] = devdocs_content
        except Exception as e:
            logger.debug("fetch_all_sources: DevDocs failed: %s", str(e)[:60])
        sources_tried.append("devdocs")

        # 3. IconStack (iconos para UIs generadas)
        try:
            iconstack_content = await self.fetch_iconstack(query)
            if iconstack_content:
                results["iconstack"] = iconstack_content
        except Exception as e:
            logger.debug("fetch_all_sources: IconStack failed: %s", str(e)[:60])
        sources_tried.append("iconstack")

        # 4. Picsum (imagenes profesionales para frontends)
        try:
            picsum_content = await self.fetch_picsum(query)
            if picsum_content:
                results["picsum"] = picsum_content
        except Exception as e:
            logger.debug("fetch_all_sources: Picsum failed: %s", str(e)[:60])
        sources_tried.append("picsum")

        # Agregar metricas y fuentes consultadas
        results["_metrics"] = self._metrics.get_stats()
        results["_sources_tried"] = sources_tried
        results["_total_sources"] = len(sources_tried)
        results["_successful_sources"] = len([
            k for k in results if k and not k.startswith("_")
        ])

        return results

    # ============================================================
    #  GITHUB METRICS API - Para monitoreo externo
    # ============================================================

    async def get_github_rate_limit(self) -> Dict[str, Any]:
        """
        Obtiene el estado del rate limit de GitHub API.

        Returns:
            dict con: core, search, error
        """
        return await self._metrics.fetch_rate_limit(self._config["github_token"])

    def get_all_metrics(self) -> Dict[str, Any]:
        """
        Retorna todas las metricas recopiladas del scraper.

        Incluye:
        - GitHub rate limit, search stats, repo stats
        - Configuracion del scraper
        - Estado del cache
        """
        return {
            "github": self._metrics.get_stats(),
            "config": {
                "timeout": self._timeout,
                "max_retries": self._max_retries,
                "max_chars": self._max_chars,
                "preferred_source": self._preferred_source,
                "has_github_token": bool(self._config["github_token"]),
                "devdocs_url": self._config["devdocs_url"],
                "iconstack_url": self._config["iconstack_url"],
                "picsum_url": self._config["picsum_url"],
            },
            "cache": {
                "size": len(self._cache),
                "max_size": 100,
            },
        }
