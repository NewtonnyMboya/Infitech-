# INFILINK Runtime

The first Runtime milestone is a bounded adapter registry, not a universal
multi-language virtual machine.

## Python reference adapter

The Python runtime module provides explicit registration of trusted in-process
async handlers, language labels, declared capabilities, a bounded registry
(default 32 adapters, maximum 256), per-call deadlines (default 5 seconds,
maximum 60), and JSON input/output validation capped at 1 MiB.

Example:

    from runtime import RegisteredHandlerAdapter, RuntimeRegistry

    async def normalize(payload):
        return {"text": payload["text"].strip().lower()}

    registry = RuntimeRegistry()
    await registry.register(
        "python-default",
        RegisteredHandlerAdapter("python", {"normalize": normalize}),
    )
    result = await registry.invoke(
        "python-default", "normalize", {"text": "  Hello IILP  "}
    )

## Security boundary

Only application code already trusted by the operator may register handlers.
The Runtime does not use eval, exec, shell commands, user-controlled imports,
or arbitrary source-code execution. A timeout bounds how long the caller waits;
it is not an OS sandbox and cannot safely stop a handler that blocks the event
loop or ignores cancellation. Untrusted workloads need separate OS/container
isolation before support can be claimed.

The language field is descriptive metadata. This milestone registers Python
handlers only; it does not execute JavaScript or other language engines. The
Node.js IILP codec remains a separate protocol binding.
