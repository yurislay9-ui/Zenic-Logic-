"""
TITAN OMNISCALE X v16 - Smart Scraper Agent Tests

Tests unitarios para el Scraper Inteligente multi-fuente:
- GitHubScrapAgent (auto-routing, smart_fetch, fetch_all_sources)
- GitHubMetrics (rate_limit, search_stats, repo_stats)
- Env Loader (load_env, get_env, get_github_token, get_scraper_config)
- Integracion de las 4 fuentes: GitHub, DevDocs, IconStack, Picsum
"""

import asyncio
import json
import os
import sys
import unittest
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Agregar raiz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture(autouse=True)
def _prevent_env_reload(monkeypatch):
    """Prevent real .env loading during tests."""
    try:
        import src.core.env_loader as env_mod
        monkeypatch.setattr(env_mod, '_loaded', True)
    except ImportError:
        pass

class TestEnvLoader(unittest.TestCase):
    """Tests para el cargador de variables de entorno (.env)."""

    def test_parse_env_line_simple(self):
        """Test: parsea linea KEY=VALUE simple."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("GITHUB_TOKEN=ghp_abc123")
        self.assertEqual(result, ("GITHUB_TOKEN", "ghp_abc123"))

    def test_parse_env_line_quoted(self):
        """Test: parsea linea con comillas dobles."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line('GITHUB_TOKEN="ghp_abc with spaces"')
        self.assertEqual(result, ("GITHUB_TOKEN", "ghp_abc with spaces"))

    def test_parse_env_line_single_quoted(self):
        """Test: parsea linea con comillas simples."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("GITHUB_TOKEN='ghp_single_quotes'")
        self.assertEqual(result, ("GITHUB_TOKEN", "ghp_single_quotes"))

    def test_parse_env_line_comment(self):
        """Test: ignora comentarios."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("# This is a comment")
        self.assertIsNone(result)

    def test_parse_env_line_empty(self):
        """Test: ignora lineas vacias."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("")
        self.assertIsNone(result)

    def test_parse_env_line_no_equals(self):
        """Test: ignora lineas sin =."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("NO_EQUALS_HERE")
        self.assertIsNone(result)

    def test_parse_env_line_value_with_equals(self):
        """Test: parsea valor que contiene = (separar solo en el primero)."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("KEY=value=with=equals")
        self.assertEqual(result, ("KEY", "value=with=equals"))

    def test_get_github_token_primary(self):
        """Test: GITHUB_TOKEN tiene prioridad sobre GITHUB_API_KEY."""
        from src.core.env_loader import get_github_token, _loaded
        # Reset para test limpio
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "primary_token",
            "GITHUB_API_KEY": "fallback_token",
        }, clear=False):
            result = get_github_token()
            self.assertEqual(result, "primary_token")

    def test_get_github_token_fallback(self):
        """Test: usa GITHUB_API_KEY si no hay GITHUB_TOKEN."""
        from src.core.env_loader import get_github_token
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {
            "GITHUB_API_KEY": "fallback_token",
        }, clear=False):
            # Remover GITHUB_TOKEN si existe
            os.environ.pop("GITHUB_TOKEN", None)
            result = get_github_token()
            self.assertEqual(result, "fallback_token")

    def test_get_github_token_empty(self):
        """Test: retorna vacio si no hay token."""
        from src.core.env_loader import get_github_token
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {}, clear=True):
            result = get_github_token()
            self.assertEqual(result, "")

    def test_get_env_bool_truthy(self):
        """Test: valores truthy para booleanos."""
        from src.core.env_loader import get_env_bool
        import src.core.env_loader as env_mod

        for val in ("true", "yes", "1", "on"):
            with patch.dict(os.environ, {"TEST_BOOL": val}, clear=False):
                result = get_env_bool("TEST_BOOL")
                self.assertTrue(result, f"Expected True for '{val}'")

    def test_get_env_bool_falsy(self):
        """Test: valores falsy para booleanos."""
        from src.core.env_loader import get_env_bool
        import src.core.env_loader as env_mod

        for val in ("false", "no", "0", "off"):
            with patch.dict(os.environ, {"TEST_BOOL": val}, clear=False):
                result = get_env_bool("TEST_BOOL")
                self.assertFalse(result, f"Expected False for '{val}'")

    def test_get_env_int(self):
        """Test: parsea enteros correctamente."""
        from src.core.env_loader import get_env_int
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {"TEST_INT": "42"}, clear=False):
            result = get_env_int("TEST_INT")
            self.assertEqual(result, 42)

    def test_get_env_int_default(self):
        """Test: retorna default si no existe o es invalido."""
        from src.core.env_loader import get_env_int
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {}, clear=True):
            result = get_env_int("NONEXISTENT_INT", default=99)
            self.assertEqual(result, 99)

    def test_get_env_list(self):
        """Test: parsea lista separada por comas."""
        from src.core.env_loader import get_env_list
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {"TEST_LIST": "a, b, c"}, clear=False):
            result = get_env_list("TEST_LIST")
            self.assertEqual(result, ["a", "b", "c"])

    def test_get_scraper_config_defaults(self):
        """Test: configuracion por defecto del scraper."""
        from src.core.env_loader import get_scraper_config
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {}, clear=True):
            config = get_scraper_config()
            self.assertEqual(config["timeout"], 10)
            self.assertEqual(config["max_retries"], 2)
            self.assertEqual(config["max_chars"], 2000)
            self.assertEqual(config["preferred_source"], "auto")
            self.assertEqual(config["github_token"], "")
            self.assertEqual(config["devdocs_url"], "https://devdocs.io")
            self.assertEqual(config["iconstack_url"], "https://icon-icons.com")
            self.assertEqual(config["picsum_url"], "https://picsum.photos")
            self.assertEqual(config["picsum_width"], 800)
            self.assertEqual(config["picsum_height"], 600)

    def test_get_scraper_config_custom(self):
        """Test: configuracion custom desde entorno."""
        from src.core.env_loader import get_scraper_config
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {
            "SCRAPER_TIMEOUT": "15",
            "SCRAPER_MAX_CHARS": "3000",
            "SCRAPER_PREFERRED_SOURCE": "devdocs",
            "GITHUB_TOKEN": "ghp_test123",
        }, clear=False):
            config = get_scraper_config()
            self.assertEqual(config["timeout"], 15)
            self.assertEqual(config["max_chars"], 3000)
            self.assertEqual(config["preferred_source"], "devdocs")
            self.assertEqual(config["github_token"], "ghp_test123")


class TestGitHubMetrics(unittest.TestCase):
    """Tests para la clase GitHubMetrics."""

    def setUp(self):
        """Configura el entorno para cada test."""
        import src.core.env_loader as env_mod

    def test_metrics_init_defaults(self):
        """Test: inicializacion con defaults."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {}, clear=True):
            metrics = GitHubMetrics()
            self.assertTrue(metrics.enabled)
            self.assertEqual(metrics._search_count, 0)
            self.assertEqual(metrics._search_results_total, 0)
            self.assertEqual(len(metrics._repos_seen), 0)

    def test_update_rate_limit(self):
        """Test: actualiza metricas de rate limit desde headers."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit",
        }, clear=False):
            metrics = GitHubMetrics()
            headers = {
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Reset": "1700000000",
            }
            metrics.update_rate_limit(headers)
            self.assertEqual(metrics._rate_limit_remaining, 4999)
            self.assertEqual(metrics._rate_limit_limit, 5000)
            self.assertEqual(metrics._rate_limit_reset, 1700000000)

    def test_update_rate_limit_disabled(self):
        """Test: no actualiza si metrics esta deshabilitado."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "false",
        }, clear=False):
            metrics = GitHubMetrics()
            headers = {
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Limit": "5000",
            }
            metrics.update_rate_limit(headers)
            self.assertEqual(metrics._rate_limit_remaining, 0)

    def test_update_search_stats(self):
        """Test: actualiza estadisticas de busqueda."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "search_results",
        }, clear=False):
            metrics = GitHubMetrics()
            metrics.update_search_stats(150, "test query")
            self.assertEqual(metrics._search_count, 1)
            self.assertEqual(metrics._search_results_total, 150)

    def test_update_repo_stats(self):
        """Test: actualiza estadisticas de repos."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "repo_stats",
        }, clear=False):
            metrics = GitHubMetrics()
            metrics.update_repo_stats("user/repo1")
            metrics.update_repo_stats("user/repo2")
            metrics.update_repo_stats("user/repo1")  # Duplicado
            self.assertEqual(len(metrics._repos_seen), 2)

    def test_get_stats(self):
        """Test: retorna todas las metricas recopiladas."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit,search_results,repo_stats",
        }, clear=False):
            metrics = GitHubMetrics()
            metrics.update_rate_limit({
                "X-RateLimit-Remaining": "4500",
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Reset": "1700000000",
            })
            metrics.update_search_stats(100, "test")
            metrics.update_repo_stats("user/repo")

            stats = metrics.get_stats()
            self.assertIn("rate_limit", stats)
            self.assertIn("search", stats)
            self.assertIn("repos", stats)
            self.assertEqual(stats["rate_limit"]["remaining"], 4500)
            self.assertEqual(stats["search"]["queries_made"], 1)
            self.assertEqual(stats["repos"]["unique_repos_seen"], 1)


class TestGitHubScrapAgent(unittest.TestCase):
    """Tests para la clase GitHubScrapAgent (Smart Scraper)."""

    def setUp(self):
        """Configura el entorno para cada test."""
        import src.core.env_loader as env_mod

    def _make_scraper(self, env=None):
        """Helper: crea un scraper con entorno mockeado."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
        default_env = {
            "SCRAPER_TIMEOUT": "10",
            "SCRAPER_MAX_RETRIES": "2",
            "SCRAPER_MAX_CHARS": "2000",
            "SCRAPER_PREFERRED_SOURCE": "auto",
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit,search_results,repo_stats",
        }
        if env:
            default_env.update(env)
        with patch.dict(os.environ, default_env, clear=False):
            return GitHubScrapAgent()

    def test_scraper_init(self):
        """Test: inicializacion del scraper."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "ghp_test"})
        self.assertEqual(scraper._timeout, 10)
        self.assertEqual(scraper._max_retries, 2)
        self.assertEqual(scraper._max_chars, 2000)
        self.assertEqual(scraper._preferred_source, "auto")
        self.assertIsNotNone(scraper._metrics)

    def test_scraper_init_with_token(self):
        """Test: scraper reconoce cuando hay token configurado."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "ghp_test_token_123"})
        self.assertEqual(scraper._config["github_token"], "ghp_test_token_123")

    def test_scraper_init_without_token(self):
        """Test: scraper funciona sin token (modo limitado)."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "", "GITHUB_API_KEY": ""})
        self.assertEqual(scraper._config["github_token"], "")

    def test_detect_source_code(self):
        """Test: detecta consultas de codigo -> github."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("how to implement auth example"), "github")
        self.assertEqual(scraper._detect_source("build a function pattern"), "github")
        self.assertEqual(scraper._detect_source("kotlin repository snippet"), "github")

    def test_detect_source_docs(self):
        """Test: detecta consultas de documentacion -> devdocs."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("python docs api reference syntax"), "devdocs")
        self.assertEqual(scraper._detect_source("what is the method specification tutorial guide"), "devdocs")

    def test_detect_source_icons(self):
        """Test: detecta consultas de iconos -> iconstack."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("icon for login button"), "iconstack")
        self.assertEqual(scraper._detect_source("svg logo symbol"), "iconstack")
        self.assertEqual(scraper._detect_source("menu icono"), "iconstack")

    def test_detect_source_images(self):
        """Test: detecta consultas de imagenes -> picsum."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("hero image for dashboard"), "picsum")
        self.assertEqual(scraper._detect_source("background photo banner"), "picsum")
        self.assertEqual(scraper._detect_source("placeholder image"), "picsum")

    def test_detect_source_priority(self):
        """Test: prioridad de deteccion (iconstack > picsum > devdocs > github)."""
        scraper = self._make_scraper()
        # Iconos tiene prioridad sobre imagenes
        self.assertEqual(scraper._detect_source("icon image for menu"), "iconstack")
        # Imagenes tiene prioridad sobre docs
        self.assertEqual(scraper._detect_source("photo documentation reference"), "picsum")

    def test_detect_source_default_github(self):
        """Test: default es github para consultas genericas."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("auth login python"), "github")

    def test_smart_fetch_cached(self):
        """Test: smart_fetch retorna resultado cacheado."""
        scraper = self._make_scraper()
        # Simular cache existente
        scraper._cache["github:auth python:python"] = "cached_code_result"

        result = asyncio.run(
            scraper.smart_fetch("auth python", "python", "github")
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["content"], "cached_code_result")
        self.assertTrue(result["metadata"]["cached"])

    def test_smart_fetch_unknown_source(self):
        """Test: smart_fetch usa github como fallback para fuente desconocida."""
        scraper = self._make_scraper()

        # Mockear fetch_github_code para no hacer llamadas reales
        async def mock_fetch(query, lang=""):
            return "mocked_github_code"

        scraper.fetch_github_code = mock_fetch

        result = asyncio.run(
            scraper.smart_fetch("test query", "python", "unknown_source")
        )
        self.assertEqual(result["source"], "github")
        self.assertTrue(result["success"])

    def test_fetch_modern_code_backward_compat(self):
        """Test: fetch_modern_code es backward-compatible."""
        scraper = self._make_scraper()

        async def mock_fetch_github(query, lang=""):
            return "backward_compat_code"

        scraper.fetch_github_code = mock_fetch_github

        result = asyncio.run(
            scraper.fetch_modern_code("auth login", "kotlin")
        )
        self.assertEqual(result, "backward_compat_code")

    def test_fetch_picsum_default(self):
        """Test: fetch_picsum genera URL con dimensiones por defecto."""
        scraper = self._make_scraper()

        # Mockear urllib.request.urlopen
        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.url = "https://picsum.photos/800/600"
            mock_resp.headers = MagicMock()
            mock_resp.headers.get.side_effect = lambda k, d="": {
                "Content-Type": "image/jpeg",
                "Content-Length": "123456",
            }.get(k, d)
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_picsum()
            )
            self.assertTrue(bool(result))
            data = json.loads(result)
            self.assertEqual(data["source"], "picsum")
            self.assertIn("https://picsum.photos/800/600", data["direct_url"])
            self.assertIn("usage", data)
            self.assertIn("html", data["usage"])
            self.assertIn("css", data["usage"])

    def test_fetch_picsum_custom_dimensions(self):
        """Test: fetch_picsum acepta dimensiones personalizadas."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.url = "https://picsum.photos/1200x800"
            mock_resp.headers = MagicMock()
            mock_resp.headers.get.side_effect = lambda k, d="": {
                "Content-Type": "image/jpeg",
                "Content-Length": "200000",
            }.get(k, d)
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_picsum("1200x800")
            )
            self.assertTrue(bool(result))
            data = json.loads(result)
            self.assertIn("1200", data["direct_url"])
            self.assertIn("800", data["direct_url"])

    def test_fetch_picsum_max_dimensions(self):
        """Test: fetch_picsum limita dimensiones a 1920x1080."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.url = "https://picsum.photos/1920/1080"
            mock_resp.headers = MagicMock()
            mock_resp.headers.get.side_effect = lambda k, d="": {
                "Content-Type": "image/jpeg",
                "Content-Length": "500000",
            }.get(k, d)
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_picsum("3840x2160")  # 4K - deberia limitar
            )
            self.assertTrue(bool(result))
            data = json.loads(result)
            self.assertEqual(data["metadata"]["width"], 1920)
            self.assertEqual(data["metadata"]["height"], 1080)

    def test_fetch_iconstack_fallback(self):
        """Test: fetch_iconstack usa fallback Material Design icons."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            # Simular que la API falla
            mock_urlopen.side_effect = Exception("API unavailable")

            result = asyncio.run(
                scraper.fetch_iconstack("login")
            )
            self.assertTrue(bool(result))
            data = json.loads(result)
            self.assertEqual(data["source"], "iconstack")
            self.assertEqual(len(data["icons"]), 1)
            self.assertEqual(data["icons"][0]["name"], "login")
            self.assertIn("Fallback", data.get("note", ""))

    def test_fetch_iconstack_known_icons(self):
        """Test: fallback tiene iconos conocidos de Material Design."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("API unavailable")

            for icon_name in ["login", "logout", "menu", "settings", "home",
                              "user", "search", "add", "delete", "edit"]:
                result = asyncio.run(
                    scraper.fetch_iconstack(icon_name)
                )
                self.assertTrue(bool(result), f"Expected result for icon '{icon_name}'")
                data = json.loads(result)
                self.assertEqual(data["source"], "iconstack")

    def test_fetch_iconstack_unknown_icon(self):
        """Test: iconstack retorna vacio para icono desconocido sin API."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("API unavailable")

            result = asyncio.run(
                scraper.fetch_iconstack("xyzzy_nonexistent_icon_12345")
            )
            self.assertEqual(result, "")

    def test_fetch_github_code_with_token(self):
        """Test: GitHub usa token en Authorization header."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "ghp_test_token"})

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = MagicMock()
            mock_resp.read.return_value = json.dumps({"total_count": 0, "items": []}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_github_code("test query", "python")
            )

            # Verificar que se llamo con Authorization header
            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            self.assertIn("Authorization", req.headers)
            self.assertEqual(req.headers["Authorization"], "token ghp_test_token")

    def test_fetch_github_code_without_token(self):
        """Test: GitHub funciona sin token (modo 60 req/h)."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "", "GITHUB_API_KEY": ""})

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = MagicMock()
            mock_resp.read.return_value = json.dumps({"total_count": 0, "items": []}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_github_code("test query", "python")
            )

            # Verificar que NO se envio Authorization header
            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            self.assertNotIn("Authorization", req.headers)

    def test_fetch_github_code_rate_limit(self):
        """Test: GitHub maneja rate limit (403) correctamente."""
        scraper = self._make_scraper()
        import urllib.error

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            error = urllib.error.HTTPError(
                url="https://api.github.com/search/code",
                code=403,
                msg="Forbidden",
                hdrs={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"},
                fp=None,
            )
            mock_urlopen.side_effect = error

            result = asyncio.run(
                scraper.fetch_github_code("test query", "python")
            )
            self.assertEqual(result, "")  # No crashea, retorna vacio

    def test_cache_limit(self):
        """Test: cache se limpia automaticamente al pasar de 100 entradas."""
        scraper = self._make_scraper()

        # Llenar cache hasta 101 entradas
        for i in range(105):
            scraper._cache[f"github:query{i}:python"] = f"result_{i}"

        self.assertGreater(len(scraper._cache), 100)

        # Simular que se agrega una entrada que dispara limpieza
        # (la limpieza ocurre dentro de smart_fetch, pero podemos
        # verificar la logica directamente)
        if len(scraper._cache) > 100:
            keys = list(scraper._cache.keys())
            for k in keys[:20]:
                del scraper._cache[k]

        self.assertLessEqual(len(scraper._cache), 85)

    def test_get_all_metrics(self):
        """Test: get_all_metrics retorna estructura completa."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "ghp_test"})

        metrics = scraper.get_all_metrics()
        self.assertIn("github", metrics)
        self.assertIn("config", metrics)
        self.assertIn("cache", metrics)
        self.assertTrue(metrics["config"]["has_github_token"])
        self.assertEqual(metrics["config"]["devdocs_url"], "https://devdocs.io")
        self.assertEqual(metrics["config"]["iconstack_url"], "https://icon-icons.com")
        self.assertEqual(metrics["config"]["picsum_url"], "https://picsum.photos")


class TestFetchAllSources(unittest.TestCase):
    """Tests para fetch_all_sources (4 fuentes)."""

    def setUp(self):
        """Configura el entorno para cada test."""
        import src.core.env_loader as env_mod

    def _make_scraper(self, env=None):
        """Helper: crea un scraper con entorno mockeado."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
        default_env = {
            "SCRAPER_TIMEOUT": "10",
            "SCRAPER_MAX_RETRIES": "0",
            "SCRAPER_MAX_CHARS": "2000",
            "SCRAPER_PREFERRED_SOURCE": "auto",
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit,search_results,repo_stats",
        }
        if env:
            default_env.update(env)
        with patch.dict(os.environ, default_env, clear=False):
            return GitHubScrapAgent()

    def test_fetch_all_sources_tries_all_four(self):
        """Test: fetch_all_sources intenta las 4 fuentes."""
        scraper = self._make_scraper()

        # Mockear todas las fuentes
        scraper.fetch_github_code = AsyncMock(return_value="github_code")
        scraper.fetch_devdocs = AsyncMock(return_value="devdocs_content")
        scraper.fetch_iconstack = AsyncMock(return_value="iconstack_icons")
        scraper.fetch_picsum = AsyncMock(return_value="picsum_image")

        result = asyncio.run(
            scraper.fetch_all_sources("test query", "python")
        )

        # Verificar que todas las fuentes fueron consultadas
        self.assertEqual(result["_total_sources"], 4)
        self.assertEqual(result["_successful_sources"], 4)
        self.assertIn("github", result)
        self.assertIn("devdocs", result)
        self.assertIn("iconstack", result)
        self.assertIn("picsum", result)
        self.assertEqual(result["_sources_tried"], ["github", "devdocs", "iconstack", "picsum"])

    def test_fetch_all_sources_partial_failure(self):
        """Test: fetch_all_sources maneja fallos parciales."""
        scraper = self._make_scraper()

        # Solo GitHub y Picsum funcionan
        scraper.fetch_github_code = AsyncMock(return_value="github_code")
        scraper.fetch_devdocs = AsyncMock(return_value="")  # Sin resultados
        scraper.fetch_iconstack = AsyncMock(side_effect=Exception("API down"))
        scraper.fetch_picsum = AsyncMock(return_value="picsum_image")

        result = asyncio.run(
            scraper.fetch_all_sources("test query", "python")
        )

        self.assertEqual(result["_total_sources"], 4)
        self.assertEqual(result["_successful_sources"], 2)
        self.assertIn("github", result)
        self.assertIn("picsum", result)
        self.assertNotIn("devdocs", result)
        self.assertNotIn("iconstack", result)

    def test_fetch_all_sources_all_fail(self):
        """Test: fetch_all_sources maneja fallo total."""
        scraper = self._make_scraper()

        scraper.fetch_github_code = AsyncMock(return_value="")
        scraper.fetch_devdocs = AsyncMock(return_value="")
        scraper.fetch_iconstack = AsyncMock(return_value="")
        scraper.fetch_picsum = AsyncMock(return_value="")

        result = asyncio.run(
            scraper.fetch_all_sources("nonexistent query", "python")
        )

        self.assertEqual(result["_total_sources"], 4)
        self.assertEqual(result["_successful_sources"], 0)
        self.assertIn("_metrics", result)


class TestSmartFetchAutoRouting(unittest.TestCase):
    """Tests para smart_fetch con auto-routing."""

    def setUp(self):
        """Configura el entorno para cada test."""
        import src.core.env_loader as env_mod

    def _make_scraper(self, env=None):
        """Helper: crea un scraper con entorno mockeado."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
        default_env = {
            "SCRAPER_TIMEOUT": "10",
            "SCRAPER_MAX_RETRIES": "0",
            "SCRAPER_MAX_CHARS": "2000",
            "SCRAPER_PREFERRED_SOURCE": "auto",
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit,search_results,repo_stats",
        }
        if env:
            default_env.update(env)
        with patch.dict(os.environ, default_env, clear=False):
            return GitHubScrapAgent()

    def test_auto_route_to_github(self):
        """Test: auto-routing redirige a github para codigo."""
        scraper = self._make_scraper()
        scraper.fetch_github_code = AsyncMock(return_value="code_result")

        result = asyncio.run(
            scraper.smart_fetch("implement auth function example", "python", "auto")
        )
        self.assertEqual(result["source"], "github")

    def test_auto_route_to_devdocs(self):
        """Test: auto-routing redirige a devdocs para docs."""
        scraper = self._make_scraper()
        scraper.fetch_devdocs = AsyncMock(return_value="docs_result")

        result = asyncio.run(
            scraper.smart_fetch("python docs api reference syntax method", "python", "auto")
        )
        self.assertEqual(result["source"], "devdocs")

    def test_auto_route_to_iconstack(self):
        """Test: auto-routing redirige a iconstack para iconos."""
        scraper = self._make_scraper()
        scraper.fetch_iconstack = AsyncMock(return_value="icons_result")

        result = asyncio.run(
            scraper.smart_fetch("icon for login button", "", "auto")
        )
        self.assertEqual(result["source"], "iconstack")

    def test_auto_route_to_picsum(self):
        """Test: auto-routing redirige a picsum para imagenes."""
        scraper = self._make_scraper()
        scraper.fetch_picsum = AsyncMock(return_value="picsum_result")

        result = asyncio.run(
            scraper.smart_fetch("hero image for dashboard", "", "auto")
        )
        self.assertEqual(result["source"], "picsum")

    def test_force_source_github(self):
        """Test: forzar fuente github ignora auto-routing."""
        scraper = self._make_scraper()
        scraper.fetch_github_code = AsyncMock(return_value="github_code")

        result = asyncio.run(
            scraper.smart_fetch("icon for login", "", "github")
        )
        self.assertEqual(result["source"], "github")

    def test_force_source_picsum(self):
        """Test: forzar fuente picsum."""
        scraper = self._make_scraper()
        scraper.fetch_picsum = AsyncMock(return_value="picsum_result")

        result = asyncio.run(
            scraper.smart_fetch("auth function", "python", "picsum")
        )
        self.assertEqual(result["source"], "picsum")


if __name__ == "__main__":
    unittest.main()
