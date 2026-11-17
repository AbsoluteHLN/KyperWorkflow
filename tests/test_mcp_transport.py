import sys
import unittest
try:
 from mcp import ClientSession, StdioServerParameters
 from mcp.client.stdio import stdio_client
 MCP_AVAILABLE=True
except ImportError:  # Optional [mcp] extra; a skip is not transport evidence.
 MCP_AVAILABLE=False
class TransportTests(unittest.IsolatedAsyncioTestCase):
 @unittest.skipUnless(MCP_AVAILABLE,'optional mcp extra is not installed')
 async def test_real_local_stdio(self):
  async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','kyper_workflow.server'])) as (read,write):
   async with ClientSession(read,write) as session:
    await session.initialize()
    listing=await session.list_tools();self.assertEqual({t.name for t in listing.tools},
      {'capabilities','setup_checklist','project_map','project_memory','review_text',
       'role_catalog','workflow_plan'})
    result=await session.call_tool('review_text',{'text':'结果已经完成。结果已经完成。','profile':'conversation_summary'})
    self.assertFalse(result.isError)
