from tools import ToolsManager

manager = ToolsManager()
print("Available tools: ")
print(manager.describe_tools())
tool, tool_response = manager.parse_tool("<|start_tool|>" + input("> ") + "<|end_tool|>")
print(tool_response)