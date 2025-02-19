from . import LlamaToolsManager

manager = LlamaToolsManager(print_errors=False)
print("Available tools: ")
print(manager.describe_tools())
while True:
    tool = manager.parse_tool("<|start_tool|>" + input("> ") + "<|end_tool|>")
    print(tool.result)