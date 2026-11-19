import asyncio
import unittest

from core import CoreError, MessageRouter, ServiceRegistry


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_discover_and_dispatch(self):
        registry = ServiceRegistry()
        async def echo(message):
            return {"echo": message["body"]["value"]}
        await registry.register("echo", echo, {"echo"})
        self.assertEqual((await registry.discover())[0]["name"], "echo")
        router = MessageRouter(registry)
        result = await router.dispatch("echo", {
            "type": "echo", "id": "test", "body": {"value": "hello"}
        })
        self.assertEqual(result, {"echo": "hello"})

    async def test_undeclared_type_is_rejected(self):
        registry = ServiceRegistry()
        async def handler(_):
            return {}
        await registry.register("safe", handler, {"read"})
        with self.assertRaises(CoreError):
            await MessageRouter(registry).dispatch(
                "safe", {"type": "execute", "id": "x", "body": {}}
            )

    async def test_capacity_is_bounded(self):
        registry = ServiceRegistry(max_services=1)
        async def handler(_):
            return {}
        await registry.register("one", handler, {"read"})
        with self.assertRaises(CoreError):
            await registry.register("two", handler, {"read"})


if __name__ == "__main__":
    unittest.main()
