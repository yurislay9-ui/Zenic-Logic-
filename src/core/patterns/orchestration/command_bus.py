"""
TITAN OMNISCALE X - Command Bus (Command Pattern)

Formal Command pattern implementation for replacing the StepDispatcher's
if/elif chain with a type-driven dispatch mechanism.

Features:
- Type-based command routing (replaces if/elif chains)
- Middleware pipeline for pre/post processing
- Validator pipeline for command validation before dispatch
- Sync, async, and batch dispatch modes
- Thread-safe handler registration and dispatch
- Statistics tracking for observability

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

import asyncio
import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

__all__ = [
    "Command",
    "CommandHandler",
    "CommandResult",
    "CommandBus",
]


# ============================================================
#  DATA CONTRACTS
# ============================================================

@dataclass
class Command:
    """
    Command payload dispatched through the CommandBus.

    Attributes:
        command_type: Identifier used to route to the correct handler.
        payload: Arbitrary data carried by the command.
        timestamp: Unix timestamp of command creation (auto-set).
        command_id: Unique identifier for this command (auto-generated).
    """
    command_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.command_type:
            raise ValueError("command_type must not be empty")


@dataclass
class CommandResult:
    """
    Result returned by a CommandHandler after processing a Command.

    Attributes:
        success: Whether the command was handled successfully.
        data: Result data from the handler.
        error: Error message if success is False.
        command_id: The ID of the command that produced this result.
    """
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    command_id: str = ""


# ============================================================
#  HANDLER INTERFACE
# ============================================================

class CommandHandler(ABC):
    """
    Abstract base class for command handlers.

    Subclasses implement `handle` to process a Command and return a CommandResult.
    Each handler is registered for a specific command_type.
    """

    @abstractmethod
    def handle(self, command: Command) -> CommandResult:
        """
        Process the given command and return a result.

        Args:
            command: The Command to process.

        Returns:
            A CommandResult indicating success or failure.
        """
        ...


# ============================================================
#  MIDDLEWARE AND VALIDATOR TYPES
# ============================================================

# Middleware: pre/post processing around command execution.
# Signature: (command, next_handler) -> CommandResult
# - command: The incoming Command
# - next_handler: Callable that invokes the next middleware or handler
CommandMiddleware = Callable[
    [Command, Callable[[Command], CommandResult]],
    CommandResult,
]

# Async variant
AsyncCommandMiddleware = Callable[
    [Command, Callable[[Command], Awaitable[CommandResult]]],
    Awaitable[CommandResult],
]

# Validator: validates a command before dispatch.
# Returns True if valid, False (or raises) if invalid.
CommandValidator = Callable[[Command], bool]


# ============================================================
#  COMMAND BUS
# ============================================================

class CommandBus:
    """
    Formal Command Bus with middleware and validation support.

    Routes commands to registered handlers based on command_type.
    Supports middleware for cross-cutting concerns and validators
    for pre-dispatch command validation.

    Usage::

        bus = CommandBus()

        class AnalyzeHandler(CommandHandler):
            def handle(self, command):
                return CommandResult(
                    success=True,
                    data={"analysis": "done"},
                    command_id=command.command_id,
                )

        bus.register("ANALYZE_STRUCTURE", AnalyzeHandler())

        result = bus.dispatch(Command(
            command_type="ANALYZE_STRUCTURE",
            payload={"target": "main.py"},
        ))

    Middleware::

        def logging_middleware(command, next_handler):
            logger.info("Dispatching: %s", command.command_type)
            result = next_handler(command)
            logger.info("Result: %s", result.success)
            return result

        bus.add_middleware(logging_middleware)

    Validators::

        def require_target(command):
            return "target" in command.payload

        bus.add_validator(require_target)

    Thread Safety:
        All operations are protected by threading.Lock.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, CommandHandler] = {}
        self._middlewares: List[CommandMiddleware] = []
        self._validators: List[CommandValidator] = []
        self._lock = threading.Lock()
        self._dispatch_count: int = 0
        self._error_count: int = 0
        self._validation_reject_count: int = 0

    # ----------------------------------------------------------
    #  HANDLER REGISTRATION
    # ----------------------------------------------------------

    def register(self, command_type: str, handler: CommandHandler) -> None:
        """
        Register a handler for a specific command type.

        Args:
            command_type: The command type this handler processes.
            handler: A CommandHandler instance.

        Raises:
            ValueError: If command_type is empty or handler is None.
        """
        if not command_type:
            raise ValueError("command_type must not be empty")
        if handler is None:
            raise ValueError("handler must not be None")

        with self._lock:
            self._handlers[command_type] = handler
            logger.info(
                "CommandBus: Registered handler %s for command_type '%s'",
                type(handler).__name__, command_type,
            )

    # ----------------------------------------------------------
    #  MIDDLEWARE
    # ----------------------------------------------------------

    def add_middleware(self, middleware_fn: CommandMiddleware) -> None:
        """
        Add middleware that wraps command handler execution.

        Middleware is executed in the order it is added. Each middleware
        receives the command and a `next` callable that invokes the
        next middleware (or the actual handler if last).

        Use middleware for:
        - Logging
        - Metrics/timing
        - Transaction management
        - Error handling wrappers

        Args:
            middleware_fn: A callable with signature
                          (command, next_handler) -> CommandResult
        """
        if middleware_fn is None:
            raise ValueError("middleware_fn must not be None")

        with self._lock:
            self._middlewares.append(middleware_fn)
            logger.debug(
                "CommandBus: Added middleware '%s'",
                getattr(middleware_fn, '__name__', repr(middleware_fn)),
            )

    # ----------------------------------------------------------
    #  VALIDATORS
    # ----------------------------------------------------------

    def add_validator(self, validator_fn: CommandValidator) -> None:
        """
        Add a validator that checks commands before dispatch.

        Validators are executed in order. If ANY validator returns
        False, the command is rejected with a validation error.

        Use validators for:
        - Input validation
        - Authorization checks
        - Schema validation

        Args:
            validator_fn: A callable with signature (command) -> bool
        """
        if validator_fn is None:
            raise ValueError("validator_fn must not be None")

        with self._lock:
            self._validators.append(validator_fn)
            logger.debug(
                "CommandBus: Added validator '%s'",
                getattr(validator_fn, '__name__', repr(validator_fn)),
            )

    # ----------------------------------------------------------
    #  VALIDATION
    # ----------------------------------------------------------

    def _validate(self, command: Command) -> Optional[str]:
        """
        Run all validators against a command.

        Args:
            command: The Command to validate.

        Returns:
            None if all validators pass, or an error message string.
        """
        with self._lock:
            validators = list(self._validators)

        for validator in validators:
            try:
                if not validator(command):
                    validator_name = getattr(
                        validator, '__name__', repr(validator)
                    )
                    return f"Validation failed: {validator_name}"
            except Exception as exc:
                validator_name = getattr(
                    validator, '__name__', repr(validator)
                )
                return f"Validation error in {validator_name}: {exc}"

        return None

    # ----------------------------------------------------------
    #  SYNC DISPATCH
    # ----------------------------------------------------------

    def dispatch(self, command: Command) -> CommandResult:
        """
        Synchronously dispatch a command to its registered handler.

        Runs validators first. If validation fails, returns an error
        CommandResult. Then applies middleware chain around the handler.

        Args:
            command: The Command to dispatch.

        Returns:
            A CommandResult from the handler (or error/validation result).
        """
        with self._lock:
            self._dispatch_count += 1
            handler = self._handlers.get(command.command_type)
            middlewares = list(self._middlewares)

        # Log dispatch
        logger.info(
            "CommandBus: Dispatching command_type='%s' id='%s' "
            "(middlewares=%d, validators=%d)",
            command.command_type, command.command_id[:8],
            len(middlewares), len(self._validators),
        )

        # Validate
        validation_error = self._validate(command)
        if validation_error is not None:
            self._validation_reject_inc()
            logger.warning(
                "CommandBus: Command '%s' rejected: %s",
                command.command_id[:8], validation_error,
            )
            return CommandResult(
                success=False,
                error=validation_error,
                command_id=command.command_id,
            )

        # Check handler exists
        if handler is None:
            error_msg = (
                f"No handler registered for command_type "
                f"'{command.command_type}'"
            )
            logger.warning("CommandBus: %s", error_msg)
            self._error_count_inc()
            return CommandResult(
                success=False,
                error=error_msg,
                command_id=command.command_id,
            )

        # Build middleware chain
        try:
            chain = _build_middleware_chain(handler.handle, middlewares)
            result = chain(command)
            return result
        except Exception as exc:
            self._error_count_inc()
            logger.error(
                "CommandBus: Handler failed for command_type '%s': %s",
                command.command_type, exc,
                exc_info=True,
            )
            return CommandResult(
                success=False,
                error=str(exc),
                command_id=command.command_id,
            )

    # ----------------------------------------------------------
    #  ASYNC DISPATCH
    # ----------------------------------------------------------

    async def dispatch_async(self, command: Command) -> CommandResult:
        """
        Asynchronously dispatch a command to its registered handler.

        Supports async handlers and middleware. Sync handlers are
        automatically wrapped to run in the default executor.

        Args:
            command: The Command to dispatch.

        Returns:
            A CommandResult from the handler (or error/validation result).
        """
        with self._lock:
            self._dispatch_count += 1
            handler = self._handlers.get(command.command_type)
            middlewares = list(self._middlewares)

        logger.info(
            "CommandBus[async]: Dispatching command_type='%s' id='%s'",
            command.command_type, command.command_id[:8],
        )

        # Validate
        validation_error = self._validate(command)
        if validation_error is not None:
            self._validation_reject_inc()
            return CommandResult(
                success=False,
                error=validation_error,
                command_id=command.command_id,
            )

        # Check handler
        if handler is None:
            error_msg = (
                f"No handler registered for command_type "
                f"'{command.command_type}'"
            )
            self._error_count_inc()
            return CommandResult(
                success=False,
                error=error_msg,
                command_id=command.command_id,
            )

        try:
            # Wrap handler as async
            async def _async_handle(cmd: Command) -> CommandResult:
                result = handler.handle(cmd)
                if asyncio.iscoroutine(result):
                    result = await result
                return result

            # Build async middleware chain
            chain: Callable[[Command], Awaitable[CommandResult]] = _async_handle

            for mw in reversed(middlewares):
                prev_chain = chain

                async def _make_async_mw(
                    cmd: Command,
                    _mw: CommandMiddleware = mw,
                    _next: Callable[
                        [Command], Awaitable[CommandResult]
                    ] = prev_chain,
                ) -> CommandResult:
                    # Run sync middleware; adapt async next
                    def _sync_next(c: Command) -> CommandResult:
                        # Run the async chain in a new event loop
                        # inside a dedicated thread to avoid
                        # "cannot run the event loop while another
                        # loop is running" errors on Xiaomi.
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=1
                        ) as pool:
                            future = pool.submit(asyncio.run, _next(c))
                            return future.result()

                    return _mw(cmd, _sync_next)

                chain = _make_async_mw  # type: ignore[assignment]

            result = await chain(command)
            return result

        except Exception as exc:
            self._error_count_inc()
            logger.error(
                "CommandBus[async]: Handler failed for command_type '%s': %s",
                command.command_type, exc,
                exc_info=True,
            )
            return CommandResult(
                success=False,
                error=str(exc),
                command_id=command.command_id,
            )

    # ----------------------------------------------------------
    #  BATCH DISPATCH
    # ----------------------------------------------------------

    def dispatch_all(self, commands: List[Command]) -> List[CommandResult]:
        """
        Synchronously dispatch multiple commands in sequence.

        Each command is dispatched independently. A failure in one
        command does not affect subsequent commands.

        Args:
            commands: List of Commands to dispatch.

        Returns:
            List of CommandResults, one per command, in order.
        """
        if not commands:
            return []

        results: List[CommandResult] = []
        logger.info(
            "CommandBus: Batch dispatching %d commands", len(commands),
        )

        for command in commands:
            result = self.dispatch(command)
            results.append(result)

        successful = sum(1 for r in results if r.success)
        logger.info(
            "CommandBus: Batch complete: %d/%d successful",
            successful, len(commands),
        )

        return results

    # ----------------------------------------------------------
    #  UTILITIES
    # ----------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """
        Runtime statistics for monitoring and debugging.

        Returns:
            Dict with:
            - dispatch_count: Total commands dispatched
            - errors_count: Total dispatch errors
            - validation_reject_count: Total commands rejected by validators
            - registered_handlers: Number of registered handlers
            - registered_types: List of registered command types
            - middleware_count: Number of registered middleware
            - validator_count: Number of registered validators
        """
        with self._lock:
            return {
                "dispatch_count": self._dispatch_count,
                "errors_count": self._error_count,
                "validation_reject_count": self._validation_reject_count,
                "registered_handlers": len(self._handlers),
                "registered_types": list(self._handlers.keys()),
                "middleware_count": len(self._middlewares),
                "validator_count": len(self._validators),
            }

    def _error_count_inc(self) -> None:
        """Increment error counter in a thread-safe manner."""
        with self._lock:
            self._error_count += 1

    def _validation_reject_inc(self) -> None:
        """Increment validation reject counter in a thread-safe manner."""
        with self._lock:
            self._validation_reject_count += 1


# ============================================================
#  HELPER: Build middleware chain
# ============================================================

def _build_middleware_chain(
    handler_fn: Callable[[Command], CommandResult],
    middlewares: List[CommandMiddleware],
) -> Callable[[Command], CommandResult]:
    """
    Build a chain of middleware wrapping a handler.

    Middleware is applied in reverse order so that the first middleware
    added is the outermost wrapper (executed first).

    Args:
        handler_fn: The actual handler callable.
        middlewares: List of middleware functions.

    Returns:
        A callable that applies all middleware then the handler.
    """
    chain = handler_fn
    for middleware in reversed(middlewares):
        chain = _wrap_middleware(chain, middleware)
    return chain


def _wrap_middleware(
    next_fn: Callable[[Command], CommandResult],
    middleware: CommandMiddleware,
) -> Callable[[Command], CommandResult]:
    """
    Wrap a handler callable with a middleware.

    Args:
        next_fn: The next handler or middleware in the chain.
        middleware: The middleware to wrap around next_fn.

    Returns:
        A new callable that applies the middleware.
    """
    def _wrapped(command: Command) -> CommandResult:
        return middleware(command, next_fn)
    return _wrapped
