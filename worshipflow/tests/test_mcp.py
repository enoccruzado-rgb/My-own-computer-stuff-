"""Starts the real MCP server over stdio and calls tools through an MCP client."""
import asyncio
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "songs", "demo", "morning-light.txt")


async def _session(fn):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    tmp = tempfile.mkdtemp()
    cfg = os.path.join(tmp, "cfg.json")
    with open(cfg, "w") as fh:
        json.dump({"output_dir": os.path.join(tmp, "out"), "audit_log": os.path.join(tmp, "audit.log"),
                   "library_dirs": [os.path.join(ROOT, "songs")]}, fh)
    params = StdioServerParameters(command=sys.executable, args=["-m", "worshipflow.mcp_server"], cwd=ROOT,
                                   env={**os.environ, "WORSHIPFLOW_CONFIG": cfg, "PROPRESENTER_PORT": "1"})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await fn(s)


def _json(result):
    return json.loads(result.content[0].text)


class McpTests(unittest.TestCase):
    def test_tools_and_create_song(self):
        async def go(s):
            names = {t.name for t in (await s.list_tools()).tools}
            self.assertIn("propresenter_create_song", names)
            self.assertNotIn("song_approve", names)
            found = _json(await s.call_tool("song_find", {"query": "morning light"}))
            self.assertGreaterEqual(found["count"], 1)
            dry = _json(await s.call_tool("propresenter_create_song", {"lyrics_path": DEMO}))
            self.assertTrue(dry["dry_run"])
            made = _json(await s.call_tool("propresenter_create_song", {"lyrics_path": DEMO, "dry_run": False}))
            self.assertEqual(made["state"], "READY_FOR_IMPORT")
            re = _json(await s.call_tool("propresenter_set_arrangement",
                                         {"pro_path": made["pro_path"], "arrangement": "V1 C V2 C B x2 C"}))
            self.assertEqual(re["arrangement"], "Verse 1, Chorus, Verse 2, Chorus, Bridge x2, Chorus")
            conn = _json(await s.call_tool("propresenter_connect", {}))
            self.assertFalse(conn["ok"])  # nothing listens on port 1: must report, not pretend
            pub = _json(await s.call_tool("song_publish", {"pro_path": made["pro_path"], "dest_dir": "/tmp"}))
            self.assertFalse(pub["ok"])  # not approved
            return names

        names = asyncio.run(_session(go))
        self.assertEqual(len(names), 22)


if __name__ == "__main__":
    unittest.main()
