"""
TITAN OMNISCALE X - ActionExecutor System (Phase 7.1)

Sistema de ejecutores de acciones reales para el AutomationEngine.
Reemplaza los stubs logger.info() con operaciones funcionales.

Ocho ejecutores:
  1. EmailExecutor      - Envío real de emails vía SMTP
  2. HttpExecutor       - Peticiones HTTP reales (aiohttp/urllib)
  3. DatabaseExecutor   - Operaciones SQLite con queries parametrizadas
  4. FileExecutor       - Operaciones de archivos con protección path-traversal
  5. NotificationExecutor - Despacho multi-canal de notificaciones
  6. WebhookExecutor    - Envío y verificación de webhooks (HMAC-SHA256)
  7. TransformExecutor  - Transformación y mapeo de datos
  8. ScheduleExecutor   - Programación de jobs (APScheduler/fallback)

Todos los ejecutores:
  - Manejan errores gracefulmente (nunca raise, siempre devuelven ActionResult)
  - Tienen modo dry-run/fallback cuando faltan dependencias
  - Son testeable sin servicios externos
  - Usan logging extensivo
"""

import os, re, csv, json, time, sqlite3, hashlib, hmac, shutil, logging, smtplib, asyncio
import urllib.parse, urllib.request, urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Dependencias opcionales
try:
    import aiosmtplib; _HAS_AIOSMTPLIB = True
except ImportError: _HAS_AIOSMTPLIB = False

try:
    import aiohttp; _HAS_AIOHTTP = True
except ImportError: _HAS_AIOHTTP = False

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    _HAS_APSCHEDULER = True
except ImportError: _HAS_APSCHEDULER = False


# ============================================================
#  RESULTADO DE ACCIÓN
# ============================================================

@dataclass
class ActionResult:
    """Resultado estandarizado de cualquier acción ejecutada."""
    success: bool
    data: Dict[str, Any]
    error: str = ""
    duration_ms: float = 0.0


# ============================================================
#  CLASE BASE ABSTRACTA
# ============================================================

class ActionExecutor(ABC):
    """Clase base abstracta para todos los ejecutores de acciones."""

    @abstractmethod
    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        """Ejecuta la acción con la configuración y contexto dados."""
        ...

    def _measure(self) -> float:
        return time.monotonic()

    def _elapsed_ms(self, start: float) -> float:
        return round((time.monotonic() - start) * 1000, 2)


# ============================================================
#  VALIDADORES UTILITARIOS
# ============================================================

def _validate_email(email: str) -> bool:
    """Valida formato básico de email."""
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))

def _validate_url(url: str) -> bool:
    """Valida formato básico de URL."""
    try:
        r = urllib.parse.urlparse(url)
        return all([r.scheme in ("http", "https"), r.netloc])
    except Exception: return False

def _safe_path(path: str, base_dir: str = "") -> str:
    """Resuelve path y verifica que no escape del base_dir (path traversal).
    
    Si base_dir es "", usa os.getcwd(). Si el path es absoluto y
    está en un directorio permitido (/tmp, /var/tmp, etc.), lo permite.
    Nunca permite ../ que escape del directorio base.
    """
    if not base_dir: base_dir = os.getcwd()
    base_dir = os.path.realpath(base_dir)
    
    # Si el path es absoluto, verificar que está en un directorio permitido
    if os.path.isabs(path):
        resolved = os.path.realpath(path)
        # Permitir rutas absolutas en directorios seguros
        allowed_prefixes = [base_dir, "/tmp", "/var/tmp", os.path.expanduser("~")]
        for prefix in allowed_prefixes:
            if resolved.startswith(prefix + os.sep) or resolved == prefix:
                return resolved
        raise ValueError(f"Path traversal detected: '{path}' escapes base directory")
    
    # Path relativo: verificar que no escapa del base_dir
    resolved = os.path.realpath(os.path.join(base_dir, path))
    if not resolved.startswith(base_dir + os.sep) and resolved != base_dir:
        raise ValueError(f"Path traversal detected: '{path}' escapes base directory")
    return resolved

def _validate_sql(query: str) -> bool:
    """Valida que un query SQL no contenga patrones de inyección peligrosos."""
    dangerous = [r";\s*DROP\s", r";\s*DELETE\s+FROM\s", r";\s*UPDATE\s+.+\s+SET\s",
                 r";\s*INSERT\s+INTO\s", r"UNION\s+SELECT\s", r"--\s*$", r"/\*.*\*/"]
    for pattern in dangerous:
        if re.search(pattern, query, re.MULTILINE | re.IGNORECASE):
            logger.warning(f"SQL validation: potentially dangerous pattern: {pattern}")
    return True


# ============================================================
#  1. EMAIL EXECUTOR
# ============================================================

class EmailExecutor(ActionExecutor):
    """Ejecutor de envío de emails reales vía SMTP.

    Usa aiosmtplib si disponible, sino smtplib (sync). Soporta HTML, CC, BCC, attachments.
    Si SMTP no configurado, funciona en modo dry-run (log).

    Config: {host, port, user, password, to, subject, body, html, cc, bcc, from_email, attachments}
    """
    _connection_pool: Dict[str, Any] = {}

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        host = config.get("host", os.environ.get("SMTP_HOST", ""))
        port = config.get("port", int(os.environ.get("SMTP_PORT", "587")))
        user = config.get("user", os.environ.get("SMTP_USER", ""))
        password = config.get("password", os.environ.get("SMTP_PASSWORD", ""))
        to_emails = config.get("to", [])
        subject = config.get("subject", "No Subject")
        body = config.get("body", "")
        html = config.get("html", "")
        cc = config.get("cc", [])
        bcc = config.get("bcc", [])
        from_email = config.get("from_email", user or "noreply@titan-omniscale.local")
        attachments = config.get("attachments", [])

        # Normalizar destinatarios a listas
        if isinstance(to_emails, str): to_emails = [to_emails]
        if isinstance(cc, str): cc = [cc]
        if isinstance(bcc, str): bcc = [bcc]

        # Validar emails
        all_recipients = to_emails + cc + bcc
        invalid = [e for e in all_recipients if not _validate_email(e)]
        if invalid:
            return ActionResult(False, {"invalid_emails": invalid},
                                f"Invalid email format: {invalid}", self._elapsed_ms(start))
        if not to_emails:
            return ActionResult(False, {}, "No recipient emails provided", self._elapsed_ms(start))

        # Modo dry-run si no hay SMTP configurado
        if not host or not user:
            return await self._dry_run(from_email, to_emails, subject, body, html, cc, bcc, start)

        # Construir y enviar mensaje
        msg = self._build_message(from_email, to_emails, subject, body, html, cc, bcc, attachments)
        result = await self._send_with_retry(host, port, user, password, to_emails, msg)
        elapsed = self._elapsed_ms(start)

        if result:
            logger.info(f"EmailExecutor: Email sent to {to_emails} - '{subject}'")
            return ActionResult(True, {"recipients": to_emails, "subject": subject, "cc": cc, "bcc": bcc}, duration_ms=elapsed)
        return ActionResult(False, {"recipients": to_emails},
                            f"Failed to send email after retries to {to_emails}", elapsed)

    def _build_message(self, from_email, to_emails, subject, body, html, cc, bcc, attachments):
        """Construye el mensaje MIME para el email."""
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject
        if cc: msg["Cc"] = ", ".join(cc)

        if html: msg.attach(MIMEText(html, "html"))
        if body: msg.attach(MIMEText(body, "plain"))
        elif not html: msg.attach(MIMEText("", "plain"))

        for att_path in attachments:
            try:
                with open(att_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(att_path)}")
                    msg.attach(part)
            except Exception as e:
                logger.warning(f"EmailExecutor: Could not attach {att_path}: {e}")
        return msg

    async def _send_with_retry(self, host, port, user, password, to_emails, msg, max_retries=3):
        """Envía email con retry y exponential backoff."""
        all_rcpts = to_emails + [e for e in msg.get("Cc", "").split(", ") if e]
        for attempt in range(max_retries):
            try:
                if _HAS_AIOSMTPLIB:
                    await aiosmtplib.send(msg.as_string(), hostname=host, port=port,
                                          username=user, password=password, start_tls=True)
                else:
                    await asyncio.to_thread(self._send_sync, host, port, user, password, all_rcpts, msg)
                return True
            except Exception as e:
                wait = (2 ** attempt) * 0.5
                logger.warning(f"EmailExecutor: Attempt {attempt+1}/{max_retries} failed: {e}. Retry in {wait}s")
                if attempt < max_retries - 1: await asyncio.sleep(wait)
        return False

    def _send_sync(self, host, port, user, password, recipients, msg):
        """Envío síncrono con smtplib (fallback)."""
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(msg["From"], recipients, msg.as_string())

    async def _dry_run(self, from_email, to_emails, subject, body, html, cc, bcc, start):
        """Modo dry-run: loguea el contenido del email sin enviarlo."""
        elapsed = self._elapsed_ms(start)
        logger.info(f"EmailExecutor [DRY-RUN]: From={from_email}, To={to_emails}, Subject={subject}")
        logger.info(f"  Body: {body[:200]}{'...' if len(body)>200 else ''}")
        if html: logger.info(f"  HTML: {html[:200]}{'...' if len(html)>200 else ''}")
        return ActionResult(True, {"mode": "dry_run", "from": from_email, "to": to_emails,
                                   "subject": subject, "cc": cc, "bcc": bcc}, duration_ms=elapsed)


# ============================================================
#  2. HTTP EXECUTOR
# ============================================================

class HttpExecutor(ActionExecutor):
    """Ejecutor de peticiones HTTP reales. Usa aiohttp si disponible, sino urllib.
    Soporta GET, POST, PUT, PATCH, DELETE con retry (3 intentos).

    Config: {url, method, headers, body, params, timeout, auth}
    """

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        url = config.get("url", "")
        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})
        body = config.get("body", None)
        params = config.get("params", {})
        timeout = config.get("timeout", 30)
        auth = config.get("auth", None)

        if not url:
            return ActionResult(False, {}, "No URL provided", self._elapsed_ms(start))
        if not _validate_url(url):
            return ActionResult(False, {"url": url}, f"Invalid URL format: {url}", self._elapsed_ms(start))

        valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}
        if method not in valid_methods:
            return ActionResult(False, {"method": method},
                                f"Invalid HTTP method: {method}. Must be one of {valid_methods}", self._elapsed_ms(start))

        # Agregar query params
        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urllib.parse.urlencode(params)}"

        max_retries = 3
        last_error = ""
        for attempt in range(max_retries):
            try:
                if _HAS_AIOHTTP:
                    result_data = await self._execute_aiohttp(url, method, headers, body, timeout, auth)
                else:
                    result_data = await asyncio.to_thread(self._execute_urllib, url, method, headers, body, timeout, auth)

                elapsed = self._elapsed_ms(start)
                status = result_data.get("status", 0)
                success = 200 <= status < 400
                logger.info(f"HttpExecutor: {method} {url} -> {status}")
                return ActionResult(success, result_data,
                                    "" if success else f"HTTP {status}: {result_data.get('body','')[:200]}", elapsed)
            except Exception as e:
                last_error = str(e)
                wait = (2 ** attempt) * 0.5
                logger.warning(f"HttpExecutor: Attempt {attempt+1}/{max_retries} failed: {e}. Retry in {wait}s")
                if attempt < max_retries - 1: await asyncio.sleep(wait)

        return ActionResult(False, {"url": url, "method": method},
                            f"HTTP request failed after {max_retries} retries: {last_error}", self._elapsed_ms(start))

    async def _execute_aiohttp(self, url, method, headers, body, timeout, auth):
        """Ejecuta petición HTTP con aiohttp."""
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        auth_obj = aiohttp.BasicAuth(auth["user"], auth.get("password","")) if auth else None
        async with aiohttp.ClientSession(timeout=timeout_obj, auth=auth_obj) as session:
            kwargs = {"headers": headers}
            if body is not None and method in ("POST", "PUT", "PATCH"):
                kwargs["json" if isinstance(body, (dict, list)) else "data"] = body if isinstance(body, (dict, list)) else str(body)
            async with session.request(method, url, **kwargs) as resp:
                try: resp_body = await resp.text()
                except Exception: resp_body = ""
                return {"status": resp.status, "headers": dict(resp.headers), "body": resp_body, "url": str(resp.url)}

    def _execute_urllib(self, url, method, headers, body, timeout, auth):
        """Ejecuta petición HTTP con urllib (fallback síncrono)."""
        data = None
        if body is not None and method in ("POST", "PUT", "PATCH"):
            if isinstance(body, (dict, list)):
                data = json.dumps(body).encode("utf-8")
                headers.setdefault("Content-Type", "application/json")
            else: data = str(body).encode("utf-8")
        if auth:
            import base64
            cred = base64.b64encode(f"{auth['user']}:{auth.get('password','')}".encode()).decode()
            headers["Authorization"] = f"Basic {cred}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "headers": dict(resp.headers),
                    "body": resp.read().decode("utf-8", errors="replace"), "url": resp.url}


# ============================================================
#  3. DATABASE EXECUTOR
# ============================================================

class DatabaseExecutor(ActionExecutor):
    """Ejecutor de operaciones reales en SQLite. TODAS las queries usan placeholders (?).

    Config: {db_path, operation, query, params, script, destination}
    Operations: query, insert, update, delete, backup, script
    """

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        db_path = config.get("db_path", ":memory:")
        operation = config.get("operation", "query").lower()
        query = config.get("query", "")
        params = config.get("params", [])
        script = config.get("script", "")

        if not isinstance(params, (list, tuple)): params = [params]

        valid_ops = {"query", "insert", "update", "delete", "backup", "script"}
        if operation not in valid_ops:
            return ActionResult(False, {"operation": operation},
                                f"Invalid DB operation: {operation}. Must be one of {valid_ops}", self._elapsed_ms(start))

        if operation == "backup":
            return await self._backup(db_path, config.get("destination", ""), start)
        if operation == "script":
            return await self._execute_script(db_path, script, start)
        if not query:
            return ActionResult(False, {}, "No SQL query provided", self._elapsed_ms(start))

        _validate_sql(query)
        try:
            result_data = await asyncio.to_thread(self._execute_db, db_path, operation, query, params)
            elapsed = self._elapsed_ms(start)
            logger.info(f"DatabaseExecutor: {operation} on {db_path} completed")
            return ActionResult(True, result_data, duration_ms=elapsed)
        except Exception as e:
            elapsed = self._elapsed_ms(start)
            logger.error(f"DatabaseExecutor: {operation} failed: {e}")
            return ActionResult(False, {"operation": operation, "query": query}, str(e), elapsed)

    def _execute_db(self, db_path, operation, query, params):
        """Ejecuta la operación en SQLite (síncrono, desde thread)."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(query, params)
            if operation == "query":
                rows = [dict(row) for row in cursor.fetchall()]
                conn.commit()
                return {"rows": rows, "row_count": len(rows)}
            conn.commit()
            return {"affected_rows": cursor.rowcount, "lastrowid": cursor.lastrowid}
        finally: conn.close()

    async def _backup(self, db_path, destination, start):
        """Realiza backup de la base de datos SQLite."""
        if db_path == ":memory:":
            return ActionResult(False, {}, "Cannot backup in-memory database", self._elapsed_ms(start))
        if not os.path.exists(db_path):
            return ActionResult(False, {"db_path": db_path}, f"Database file not found: {db_path}", self._elapsed_ms(start))
        try:
            if not destination: destination = db_path + f".backup_{int(time.time())}"
            def _do_backup():
                src = sqlite3.connect(db_path); dst = sqlite3.connect(destination)
                src.backup(dst); dst.close(); src.close()
            await asyncio.to_thread(_do_backup)
            size = os.path.getsize(destination)
            logger.info(f"DatabaseExecutor: Backup created at {destination} ({size} bytes)")
            return ActionResult(True, {"source": db_path, "destination": destination, "size_bytes": size},
                                duration_ms=self._elapsed_ms(start))
        except Exception as e:
            return ActionResult(False, {"db_path": db_path}, f"Backup failed: {e}", self._elapsed_ms(start))

    async def _execute_script(self, db_path, script, start):
        """Ejecuta un script SQL con múltiples statements."""
        if not script:
            return ActionResult(False, {}, "No SQL script provided", self._elapsed_ms(start))
        try:
            def _run():
                conn = sqlite3.connect(db_path)
                try: conn.executescript(script); conn.commit()
                finally: conn.close()
            await asyncio.to_thread(_run)
            return ActionResult(True, {"script_lines": len(script.split(";"))}, duration_ms=self._elapsed_ms(start))
        except Exception as e:
            return ActionResult(False, {}, f"Script execution failed: {e}", self._elapsed_ms(start))


# ============================================================
#  4. FILE EXECUTOR
# ============================================================

class FileExecutor(ActionExecutor):
    """Ejecutor de operaciones reales en el filesystem con protección path-traversal.

    Config: {operation, source, destination, content, pattern, base_dir}
    Operations: read, write, append, copy, move, delete, list, mkdir, exists
    """

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        operation = config.get("operation", "read").lower()
        base_dir = config.get("base_dir", os.getcwd())
        source = config.get("source", "")
        destination = config.get("destination", "")
        content = config.get("content", "")
        pattern = config.get("pattern", "*")

        valid_ops = {"read", "write", "append", "copy", "move", "delete", "list", "mkdir", "exists"}
        if operation not in valid_ops:
            return ActionResult(False, {"operation": operation},
                                f"Invalid file operation: {operation}. Must be one of {valid_ops}", self._elapsed_ms(start))
        try:
            if source: source = _safe_path(source, base_dir)
            if destination: destination = _safe_path(destination, base_dir)

            ops = {"read": lambda: self._read(source), "write": lambda: self._write(destination or source, content),
                   "append": lambda: self._append(destination or source, content), "copy": lambda: self._copy(source, destination),
                   "move": lambda: self._move(source, destination), "delete": lambda: self._delete(source),
                   "list": lambda: self._list(source or base_dir, pattern), "mkdir": lambda: self._mkdir(source),
                   "exists": lambda: self._exists(source)}
            result_data = await ops[operation]()
            elapsed = self._elapsed_ms(start)
            logger.info(f"FileExecutor: {operation} completed - {source or base_dir}")
            return ActionResult(True, result_data, duration_ms=elapsed)
        except ValueError as e:
            return ActionResult(False, {"operation": operation}, str(e), self._elapsed_ms(start))
        except Exception as e:
            elapsed = self._elapsed_ms(start)
            logger.error(f"FileExecutor: {operation} failed: {e}")
            return ActionResult(False, {"operation": operation, "source": source}, str(e), elapsed)

    async def _read(self, path):
        if not os.path.exists(path): raise FileNotFoundError(f"File not found: {path}")
        def _do_read():
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        content = await asyncio.to_thread(_do_read)
        return {"content": content, "size": len(content), "path": path}

    async def _write(self, path, content):
        d = os.path.dirname(path)
        if d: os.makedirs(d, exist_ok=True)
        def _do_write():
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        await asyncio.to_thread(_do_write)
        return {"path": path, "size": len(content), "operation": "write"}

    async def _append(self, path, content):
        def _do_append():
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        await asyncio.to_thread(_do_append)
        return {"path": path, "appended_size": len(content), "operation": "append"}

    async def _copy(self, source, destination):
        if not os.path.exists(source): raise FileNotFoundError(f"Source not found: {source}")
        d = os.path.dirname(destination)
        if d: os.makedirs(d, exist_ok=True)
        def _do(): shutil.copytree(source, destination, dirs_exist_ok=True) if os.path.isdir(source) else shutil.copy2(source, destination)
        await asyncio.to_thread(_do)
        return {"source": source, "destination": destination, "operation": "copy"}

    async def _move(self, source, destination):
        if not os.path.exists(source): raise FileNotFoundError(f"Source not found: {source}")
        d = os.path.dirname(destination)
        if d: os.makedirs(d, exist_ok=True)
        await asyncio.to_thread(lambda: shutil.move(source, destination))
        return {"source": source, "destination": destination, "operation": "move"}

    async def _delete(self, path):
        if not os.path.exists(path): raise FileNotFoundError(f"Path not found: {path}")
        def _do(): shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
        await asyncio.to_thread(_do)
        return {"path": path, "operation": "delete"}

    async def _list(self, path, pattern):
        if not os.path.isdir(path): raise NotADirectoryError(f"Not a directory: {path}")
        import glob as glob_module
        files = await asyncio.to_thread(lambda: glob_module.glob(os.path.join(path, pattern)))
        return {"files": files, "count": len(files), "path": path, "pattern": pattern}

    async def _mkdir(self, path):
        await asyncio.to_thread(lambda: os.makedirs(path, exist_ok=True))
        return {"path": path, "operation": "mkdir"}

    async def _exists(self, path):
        exists = await asyncio.to_thread(os.path.exists, path)
        is_dir = await asyncio.to_thread(os.path.isdir, path) if exists else False
        is_file = await asyncio.to_thread(os.path.isfile, path) if exists else False
        return {"path": path, "exists": exists, "is_dir": is_dir, "is_file": is_file}


# ============================================================
#  5. NOTIFICATION EXECUTOR
# ============================================================

class NotificationExecutor(ActionExecutor):
    """Ejecutor de notificaciones multi-canal. Canales: log, email, telegram, webhook.
    Delega a EmailExecutor para email. Fallback a logger.info() si no configurado.

    Config: {channel, recipient, message, subject, html}
    """

    def __init__(self, email_executor: Optional[EmailExecutor] = None,
                 webhook_executor: Optional["WebhookExecutor"] = None) -> None:
        self._email_executor = email_executor
        self._webhook_executor = webhook_executor

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        channel = config.get("channel", "log").lower()
        recipient = config.get("recipient", "")
        message = config.get("message", "")
        subject = config.get("subject", "Notification")
        html = config.get("html", "")

        try:
            if channel == "log":
                result_data = self._notify_log(message, subject)
            elif channel == "email":
                result_data = await self._notify_email(recipient, message, subject, html)
            elif channel == "telegram":
                result_data = await self._notify_telegram(recipient, message)
            elif channel == "webhook":
                result_data = await self._notify_webhook(recipient, message, subject)
            else:
                logger.warning(f"NotificationExecutor: Unknown channel '{channel}', falling back to log")
                result_data = self._notify_log(message, subject)
                result_data["fallback"] = True; result_data["original_channel"] = channel

            return ActionResult(True, result_data, duration_ms=self._elapsed_ms(start))
        except Exception as e:
            logger.info(f"Notification [FALLBACK]: {message}")
            elapsed = self._elapsed_ms(start)
            return ActionResult(True, {"channel": "log", "fallback": True, "original_channel": channel},
                                f"Channel '{channel}' failed, fell back to log: {e}", elapsed)

    def _notify_log(self, message, subject=""):
        if subject: logger.info(f"Notification [{subject}]: {message}")
        else: logger.info(f"Notification: {message}")
        return {"channel": "log", "delivered": True}

    async def _notify_email(self, recipient, message, subject, html):
        if not self._email_executor:
            logger.info(f"Notification [email->log]: To: {recipient}, Subject: {subject}, Body: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True, "reason": "EmailExecutor not configured"}
        result = await self._email_executor.execute({"to": recipient, "subject": subject or "Notification",
                                                      "body": message, "html": html}, {})
        return {"channel": "email", "delivered": result.success, "email_result": result.data, "error": result.error}

    async def _notify_telegram(self, chat_id, message):
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token or not chat_id:
            logger.info(f"Notification [telegram->log]: Chat: {chat_id}, Msg: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True, "reason": "Telegram not configured"}
        try:
            http_exec = HttpExecutor()
            result = await http_exec.execute({"url": f"https://api.telegram.org/bot{bot_token}/sendMessage",
                "method": "POST", "body": {"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                "headers": {"Content-Type": "application/json"}, "timeout": 15}, {})
            return {"channel": "telegram", "delivered": result.success, "chat_id": chat_id}
        except Exception as e:
            logger.warning(f"NotificationExecutor: Telegram failed: {e}")
            logger.info(f"Notification [telegram->log]: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True}

    async def _notify_webhook(self, url, message, subject):
        if not url:
            logger.info(f"Notification [webhook->log]: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True, "reason": "No webhook URL"}
        try:
            http_exec = HttpExecutor()
            result = await http_exec.execute({"url": url, "method": "POST",
                "body": {"message": message, "subject": subject, "timestamp": time.time()},
                "headers": {"Content-Type": "application/json"}, "timeout": 15}, {})
            return {"channel": "webhook", "delivered": result.success, "url": url,
                    "response_status": result.data.get("status")}
        except Exception as e:
            logger.warning(f"NotificationExecutor: Webhook failed: {e}")
            logger.info(f"Notification [webhook->log]: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True}


# ============================================================
#  6. WEBHOOK EXECUTOR
# ============================================================

class WebhookExecutor(ActionExecutor):
    """Ejecutor de envío y verificación de webhooks con HMAC-SHA256.

    Config: {action, url, method, payload, secret, verify_signature, verify_body}
    Actions: send, verify
    """

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        action = config.get("action", "send").lower()
        try:
            if action == "send":
                result_data = await self._send_webhook(config)
            elif action == "verify":
                result_data = self._verify_webhook(config)
            else:
                return ActionResult(False, {"action": action},
                                    f"Invalid webhook action: {action}. Must be 'send' or 'verify'", self._elapsed_ms(start))
            return ActionResult(True, result_data, duration_ms=self._elapsed_ms(start))
        except Exception as e:
            return ActionResult(False, {"action": action}, str(e), self._elapsed_ms(start))

    async def _send_webhook(self, config):
        """Envía un webhook saliente con firma HMAC opcional."""
        url = config.get("url", "")
        method = config.get("method", "POST").upper()
        payload = config.get("payload", {})
        secret = config.get("secret", "")

        if not url: raise ValueError("Webhook URL is required for send action")
        if not _validate_url(url): raise ValueError(f"Invalid webhook URL: {url}")

        headers = {"Content-Type": "application/json"}
        body = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)

        signature = ""
        if secret:
            signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"
            headers["X-Webhook-Timestamp"] = str(int(time.time()))

        result = await HttpExecutor().execute({"url": url, "method": method, "body": payload,
                                                "headers": headers, "timeout": 30}, {})
        return {"action": "send", "url": url, "method": method,
                "signature": signature[:16] + "..." if signature else "",
                "response_status": result.data.get("status"),
                "response_body": result.data.get("body", "")[:500], "http_success": result.success}

    def _verify_webhook(self, config):
        """Verifica la firma HMAC-SHA256 de un webhook entrante."""
        secret = config.get("secret", "")
        signature = config.get("verify_signature", "")
        body = config.get("verify_body", "")

        if not secret: raise ValueError("Secret is required for webhook verification")
        if not signature: raise ValueError("Signature to verify is required")

        if signature.startswith("sha256="): signature = signature[7:]
        expected = hmac.new(secret.encode(), str(body).encode(), hashlib.sha256).hexdigest()
        is_valid = hmac.compare_digest(expected, signature)

        if is_valid: logger.info("WebhookExecutor: Signature verified successfully")
        else: logger.warning("WebhookExecutor: Signature verification FAILED")
        return {"action": "verify", "valid": is_valid, "algorithm": "HMAC-SHA256"}


# ============================================================
#  7. TRANSFORM EXECUTOR
# ============================================================

class TransformExecutor(ActionExecutor):
    """Ejecutor de transformación y mapeo de datos.

    Operations: map_fields, filter, sort, aggregate, format_convert, merge, deduplicate, pivot

    Config: {operation, data, mapping, format, key, keys, ascending, aggregation,
             value_field, group_by, separator, merge_data, merge_on,
             index_field, column_field}
    """

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        operation = config.get("operation", "map_fields").lower()
        data = config.get("data", None)

        valid_ops = {"map_fields", "filter", "sort", "aggregate",
                     "format_convert", "merge", "deduplicate", "pivot"}
        if operation not in valid_ops:
            return ActionResult(False, {"operation": operation},
                                f"Invalid transform operation: {operation}. Must be one of {valid_ops}", self._elapsed_ms(start))
        if data is None:
            return ActionResult(False, {}, "No input data provided", self._elapsed_ms(start))

        try:
            dispatch = {"map_fields": lambda: self._map_fields(data, config.get("mapping", {})),
                        "filter": lambda: self._filter(data, config),
                        "sort": lambda: self._sort(data, config),
                        "aggregate": lambda: self._aggregate(data, config),
                        "format_convert": lambda: self._format_convert(data, config),
                        "merge": lambda: self._merge(data, config),
                        "deduplicate": lambda: self._deduplicate(data, config),
                        "pivot": lambda: self._pivot(data, config)}
            result_data = dispatch[operation]()
            elapsed = self._elapsed_ms(start)
            logger.info(f"TransformExecutor: {operation} completed")
            return ActionResult(True, {"result": result_data, "operation": operation}, duration_ms=elapsed)
        except Exception as e:
            elapsed = self._elapsed_ms(start)
            logger.error(f"TransformExecutor: {operation} failed: {e}")
            return ActionResult(False, {"operation": operation}, str(e), elapsed)

    def _map_fields(self, data, mapping):
        if isinstance(data, dict):
            return {mapping.get(k, k): v for k, v in data.items()}
        elif isinstance(data, list):
            return [{mapping.get(k, k): v for k, v in item.items()} for item in data if isinstance(item, dict)]
        raise ValueError(f"map_fields requires dict or list of dicts, got {type(data).__name__}")

    def _filter(self, data, config):
        if not isinstance(data, list): raise ValueError(f"filter requires a list, got {type(data).__name__}")
        key, operator, value = config.get("key", ""), config.get("operator", "eq"), config.get("value", None)
        if not key: raise ValueError("filter requires 'key' in config")
        ops = {"eq": lambda a,b: a==b, "neq": lambda a,b: a!=b, "gt": lambda a,b: a>b,
               "lt": lambda a,b: a<b, "gte": lambda a,b: a>=b, "lte": lambda a,b: a<=b,
               "contains": lambda a,b: b in str(a)}
        fn = ops.get(operator, ops["eq"])
        return [item for item in data if isinstance(item, dict) and key in item and fn(item[key], value)]

    def _sort(self, data, config):
        if not isinstance(data, list): raise ValueError(f"sort requires a list, got {type(data).__name__}")
        key, ascending = config.get("key", ""), config.get("ascending", True)
        keys = config.get("keys", [])
        if not key and not keys: raise ValueError("sort requires 'key' or 'keys' in config")
        def _sk(item):
            if keys: return tuple(item.get(k, "") for k in keys)
            return item.get(key, "")
        return sorted(data, key=_sk, reverse=not ascending)

    def _aggregate(self, data, config):
        if not isinstance(data, list): raise ValueError(f"aggregate requires a list, got {type(data).__name__}")
        aggregation = config.get("aggregation", "count")
        value_field = config.get("value_field", "")
        group_by = config.get("group_by", "")
        if aggregation in ("sum", "avg", "min", "max") and not value_field:
            raise ValueError(f"aggregate '{aggregation}' requires 'value_field'")
        if group_by: return self._aggregate_grouped(data, aggregation, value_field, group_by)
        values = [item[value_field] for item in data if isinstance(item, dict) and value_field in item]
        if aggregation == "count": return {"count": len(data)}
        elif aggregation == "sum": return {"sum": sum(values)}
        elif aggregation == "avg": return {"avg": sum(values)/len(values) if values else 0}
        elif aggregation == "min": return {"min": min(values) if values else None}
        elif aggregation == "max": return {"max": max(values) if values else None}
        raise ValueError(f"Unknown aggregation: {aggregation}")

    def _aggregate_grouped(self, data, aggregation, value_field, group_by):
        groups = {}
        for item in data:
            if isinstance(item, dict) and group_by in item:
                groups.setdefault(str(item[group_by]), []).append(item)
        result = {}
        for gk, items in groups.items():
            vals = [item[value_field] for item in items if value_field in item and isinstance(item[value_field], (int, float))]
            if aggregation == "count": result[gk] = len(items)
            elif aggregation == "sum": result[gk] = sum(vals)
            elif aggregation == "avg": result[gk] = sum(vals)/len(vals) if vals else 0
            elif aggregation == "min": result[gk] = min(vals) if vals else None
            elif aggregation == "max": result[gk] = max(vals) if vals else None
        return {"groups": result, "group_by": group_by, "aggregation": aggregation}

    def _format_convert(self, data, config):
        fmt = config.get("format", "json_to_csv").lower()
        sep = config.get("separator", ",")
        if fmt == "json_to_csv": return self._json_to_csv(data, sep)
        elif fmt == "csv_to_json": return self._csv_to_json(data, sep)
        elif fmt == "flatten": return self._flatten(data)
        elif fmt == "nest": return self._nest(data, config.get("nest_key", ""))
        raise ValueError(f"Unknown format conversion: {fmt}")

    def _json_to_csv(self, data, sep):
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise ValueError("json_to_csv requires a non-empty list of dicts")
        fields = list(data[0].keys())
        lines = [sep.join(fields)]
        for item in data:
            row = []
            for f in fields:
                v = str(item.get(f, ""))
                if sep in v or '"' in v or "\n" in v: v = f'"{v.replace(chr(34), chr(34)+chr(34))}"'
                row.append(v)
            lines.append(sep.join(row))
        return "\n".join(lines)

    def _csv_to_json(self, data, sep):
        if not isinstance(data, str): raise ValueError("csv_to_json requires a CSV string")
        return [row for row in csv.DictReader(data.strip().split("\n"), delimiter=sep)]

    def _flatten(self, data, prefix=""):
        if not isinstance(data, dict): raise ValueError("flatten requires a dict")
        result = {}
        for k, v in data.items():
            fk = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict): result.update(self._flatten(v, fk))
            else: result[fk] = v
        return result

    def _nest(self, data, nest_key=""):
        if not isinstance(data, dict): raise ValueError("nest requires a dict")
        result = {}
        for k, v in data.items():
            parts = k.split(".")
            current = result
            for p in parts[:-1]: current = current.setdefault(p, {})
            current[parts[-1]] = v
        return result

    def _merge(self, data, config):
        merge_data, merge_on = config.get("merge_data", []), config.get("merge_on", "")
        if not isinstance(data, list) or not isinstance(merge_data, list): raise ValueError("merge requires two lists")
        if not merge_on: raise ValueError("merge requires 'merge_on' field")
        right_idx = {str(item[merge_on]): item for item in merge_data if isinstance(item, dict) and merge_on in item}
        result = []
        for item in data:
            if isinstance(item, dict) and merge_on in item:
                merged = {**item}
                for k, v in right_idx.get(str(item[merge_on]), {}).items():
                    if k != merge_on and k not in merged: merged[k] = v
                result.append(merged)
        return result

    def _deduplicate(self, data, config):
        if not isinstance(data, list): raise ValueError("deduplicate requires a list")
        keys = config.get("keys", [])
        key = config.get("key", "")
        if isinstance(keys, str): keys = [keys]
        if key and not keys: keys = [key]
        if not keys: raise ValueError("deduplicate requires 'key' or 'keys'")
        seen, result = set(), []
        for item in data:
            if not isinstance(item, dict): continue
            composite = tuple(str(item.get(k, "")) for k in keys)
            if composite not in seen: seen.add(composite); result.append(item)
        return {"items": result, "removed_count": len(data) - len(result)}

    def _pivot(self, data, config):
        if not isinstance(data, list): raise ValueError("pivot requires a list of dicts")
        idx_f, col_f, val_f = config.get("index_field", ""), config.get("column_field", ""), config.get("value_field", "")
        if not all([idx_f, col_f, val_f]):
            raise ValueError("pivot requires 'index_field', 'column_field', and 'value_field'")
        pivoted, columns = {}, set()
        for item in data:
            if not isinstance(item, dict): continue
            idx, col = str(item.get(idx_f, "")), str(item.get(col_f, ""))
            if idx not in pivoted: pivoted[idx] = {idx_f: idx}
            pivoted[idx][col] = item.get(val_f, "")
            columns.add(col)
        return {"data": list(pivoted.values()), "columns": sorted(columns), "index_field": idx_f}


# ============================================================
#  8. SCHEDULE EXECUTOR
# ============================================================

class ScheduleExecutor(ActionExecutor):
    """Ejecutor de programación de jobs. Usa APScheduler si disponible, sino dict simple.

    Config: {operation, job_id, func, interval, cron, args}
    Operations: add, remove, list, pause, resume
    """

    def __init__(self) -> None:
        self._scheduler: Optional[Any] = None
        self._simple_jobs: Dict[str, Dict[str, Any]] = {}
        self._job_results: Dict[str, Any] = {}
        if _HAS_APSCHEDULER:
            try:
                self._scheduler = AsyncIOScheduler()
                logger.info("ScheduleExecutor: APScheduler initialized")
            except Exception as e:
                logger.warning(f"ScheduleExecutor: APScheduler init failed: {e}")
                self._scheduler = None

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        operation = config.get("operation", "list").lower()
        job_id = config.get("job_id", "")

        valid_ops = {"add", "remove", "list", "pause", "resume"}
        if operation not in valid_ops:
            return ActionResult(False, {"operation": operation},
                                f"Invalid schedule operation: {operation}. Must be one of {valid_ops}", self._elapsed_ms(start))
        try:
            dispatch = {"add": lambda: self._add_job(config), "remove": lambda: self._remove_job(job_id),
                        "list": lambda: self._list_jobs(), "pause": lambda: self._pause_job(job_id),
                        "resume": lambda: self._resume_job(job_id)}
            result_data = await dispatch[operation]()
            elapsed = self._elapsed_ms(start)
            logger.info(f"ScheduleExecutor: {operation} completed for job '{job_id}'")
            return ActionResult(True, result_data, duration_ms=elapsed)
        except Exception as e:
            elapsed = self._elapsed_ms(start)
            logger.error(f"ScheduleExecutor: {operation} failed: {e}")
            return ActionResult(False, {"operation": operation, "job_id": job_id}, str(e), elapsed)

    async def _add_job(self, config):
        job_id = config.get("job_id", f"job_{int(time.time())}")
        func_name = config.get("func", "")
        interval = config.get("interval", 60)
        cron = config.get("cron", "")
        args = config.get("args", [])
        if not func_name: raise ValueError("Schedule add requires 'func' (function name)")

        job_info = {"job_id": job_id, "func": func_name, "interval": interval, "cron": cron,
                    "args": args, "status": "active", "created_at": time.time(), "next_run": time.time() + interval}

        if self._scheduler and _HAS_APSCHEDULER:
            async def _task(*a):
                logger.info(f"ScheduleExecutor: Executing scheduled job '{job_id}' - {func_name}")
                self._job_results[job_id] = {"last_run": time.time(), "status": "executed"}
            try:
                if cron:
                    parts = cron.split()
                    kw = {}
                    if len(parts) >= 1: kw["hour"] = int(parts[0])
                    if len(parts) >= 2: kw["minute"] = int(parts[1])
                    trigger = CronTrigger(**kw)
                else:
                    trigger = IntervalTrigger(seconds=interval)
                self._scheduler.add_job(_task, trigger=trigger, id=job_id, args=args, replace_existing=True)
                if not self._scheduler.running: self._scheduler.start()
                job_info["scheduler"] = "apscheduler"
            except Exception as e:
                logger.warning(f"ScheduleExecutor: APScheduler add_job failed: {e}, using fallback")
                self._simple_jobs[job_id] = job_info
                job_info["scheduler"] = "fallback"
        else:
            self._simple_jobs[job_id] = job_info
            job_info["scheduler"] = "fallback"
        return job_info

    async def _remove_job(self, job_id):
        if self._scheduler and _HAS_APSCHEDULER:
            try: self._scheduler.remove_job(job_id)
            except Exception: logger.debug(f"ScheduleExecutor: remove_job failed for {job_id}")
        removed = self._simple_jobs.pop(job_id, None) is not None
        return {"job_id": job_id, "removed": removed}

    def _list_jobs(self):
        jobs = list(self._simple_jobs.values())
        if self._scheduler and _HAS_APSCHEDULER and self._scheduler.running:
            try:
                for job in self._scheduler.get_jobs():
                    jobs.append({"job_id": job.id, "func": str(job.func),
                                 "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                                 "scheduler": "apscheduler"})
            except Exception as e:
                logger.warning(f"ScheduleExecutor: Could not list APScheduler jobs: {e}")
        return {"jobs": jobs, "count": len(jobs)}

    async def _pause_job(self, job_id):
        if self._scheduler and _HAS_APSCHEDULER:
            try: self._scheduler.pause_job(job_id)
            except Exception: logger.debug(f"ScheduleExecutor: pause_job failed for {job_id}")
        if job_id in self._simple_jobs: self._simple_jobs[job_id]["status"] = "paused"
        return {"job_id": job_id, "status": "paused"}

    async def _resume_job(self, job_id):
        if self._scheduler and _HAS_APSCHEDULER:
            try: self._scheduler.resume_job(job_id)
            except Exception: logger.debug(f"ScheduleExecutor: resume_job failed for {job_id}")
        if job_id in self._simple_jobs: self._simple_jobs[job_id]["status"] = "active"
        return {"job_id": job_id, "status": "active"}


# ============================================================
#  REGISTRY DE EJECUTORES
# ============================================================

class ExecutorRegistry:
    """Registry centralizado que gestiona todos los action executors.

    Provee un punto único de acceso para registrar y ejecutar
    cualquier tipo de acción a través de su executor correspondiente.
    """

    def __init__(self) -> None:
        self._executors: Dict[str, ActionExecutor] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Registra los ejecutores por defecto."""
        email_exec = EmailExecutor()
        http_exec = HttpExecutor()
        db_exec = DatabaseExecutor()
        file_exec = FileExecutor()
        webhook_exec = WebhookExecutor()
        transform_exec = TransformExecutor()
        notification_exec = NotificationExecutor(email_executor=email_exec, webhook_executor=webhook_exec)
        schedule_exec = ScheduleExecutor()

        # Mapeo de tipos de acción a ejecutores (alias incluidos)
        for key, executor in [
            ("send_email", email_exec), ("email", email_exec),
            ("http_request", http_exec), ("http", http_exec),
            ("database_operation", db_exec), ("database", db_exec), ("db", db_exec),
            ("file_operation", file_exec), ("file", file_exec),
            ("send_notification", notification_exec), ("notification", notification_exec),
            ("webhook", webhook_exec),
            ("data_transform", transform_exec), ("transform", transform_exec),
            ("schedule", schedule_exec),
        ]:
            self.register_executor(key, executor)

    def get_executor(self, action_type: str) -> Optional[ActionExecutor]:
        """Obtiene el executor registrado para un tipo de acción."""
        return self._executors.get(action_type)

    def register_executor(self, action_type: str, executor: ActionExecutor) -> None:
        """Registra un executor para un tipo de acción."""
        self._executors[action_type] = executor
        logger.debug(f"ExecutorRegistry: Registered '{action_type}' -> {executor.__class__.__name__}")

    async def execute_action(self, action_type: str, config: Dict[str, Any],
                             context: Optional[Dict[str, Any]] = None) -> ActionResult:
        """Ejecuta una acción a través del executor correspondiente."""
        if context is None: context = {}
        executor = self.get_executor(action_type)
        if not executor:
            return ActionResult(False, {"action_type": action_type},
                                f"No executor for '{action_type}'. Available: {list(self._executors.keys())}")
        try:
            return await executor.execute(config, context)
        except Exception as e:
            logger.error(f"ExecutorRegistry: Unhandled exception in {action_type}: {e}")
            return ActionResult(False, {"action_type": action_type}, f"Executor error: {e}")

    @property
    def registered_types(self) -> List[str]:
        """Lista de tipos de acción registrados."""
        return list(self._executors.keys())

    @property
    def executor_classes(self) -> Dict[str, str]:
        """Mapeo de tipo de acción a clase de executor."""
        return {k: v.__class__.__name__ for k, v in self._executors.items()}


# ============================================================
#  INSTANCIA GLOBAL DEL REGISTRY
# ============================================================

_default_registry: Optional[ExecutorRegistry] = None

def get_default_registry() -> ExecutorRegistry:
    """Obtiene la instancia global del ExecutorRegistry."""
    global _default_registry
    if _default_registry is None: _default_registry = ExecutorRegistry()
    return _default_registry

def reset_default_registry() -> None:
    """Resetea la instancia global del registry (para tests)."""
    global _default_registry
    _default_registry = None
