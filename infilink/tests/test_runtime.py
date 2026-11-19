import asyncio
import unittest
from runtime import RegisteredHandlerAdapter, RuntimeErrorBase, RuntimeRegistry, RuntimeUnavailable

class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_capability_invocation(self):
        async def uppercase(payload):
            return {"value": payload["value"].upper()}
        registry = RuntimeRegistry()
        await registry.register("python-main", RegisteredHandlerAdapter("python", {"uppercase": uppercase}))
        self.assertEqual(await registry.invoke("python-main", "uppercase", {"value": "infilink"}),
                         {"value": "INFILINK"})
        self.assertEqual((await registry.discover())[0]["language"], "python")

    async def test_unknown_runtime_and_capability_rejected(self):
        async def handler(_):
            return {}
        registry = RuntimeRegistry()
        await registry.register("py", RegisteredHandlerAdapter("python", {"read": handler}))
        with self.assertRaises(RuntimeUnavailable):
            await registry.invoke("missing", "read", {})
        with self.assertRaises(RuntimeUnavailable):
            await registry.invoke("py", "execute", {})

    async def test_timeout_is_enforced(self):
        async def slow(_):
            await asyncio.sleep(0.05)
            return {}
        registry = RuntimeRegistry(timeout_seconds=0.01)
        await registry.register("py", RegisteredHandlerAdapter("python", {"slow": slow}))
        with self.assertRaisesRegex(RuntimeErrorBase, "timed out"):
            await registry.invoke("py", "slow", {})

    async def test_payload_size_and_non_json_are_rejected(self):
        async def echo(payload):
            return payload
        registry = RuntimeRegistry()
        await registry.register("py", RegisteredHandlerAdapter("python", {"echo": echo}))
        with self.assertRaises(ValueError):
            await registry.invoke("py", "echo", {"data": "x" * 1_048_577})
        with self.assertRaises(ValueError):
            await registry.invoke("py", "echo", {"value": float("nan")})

    async def test_registry_capacity(self):
        async def handler(_):
            return {}
        registry = RuntimeRegistry(max_runtimes=1)
        adapter = RegisteredHandlerAdapter("python", {"read": handler})
        await registry.register("one", adapter)
        with self.assertRaises(RuntimeErrorBase):
            await registry.register("two", adapter)

if __name__ == "__main__":
    unittest.main()
