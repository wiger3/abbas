import os
import ast
import inspect
import asyncio
import importlib
import importlib.util
from traceback import format_exc
from abc import ABC, abstractmethod
from typing import Callable, Optional

class ToolsManager(ABC):
    def __init__(self):
        tools_dir = os.path.dirname(__file__)
        self.available_tools = {}
        for file in os.listdir(tools_dir):
            if file.startswith('_'):
                continue
            if not file.endswith('.py'):
                continue
            tool = file.rsplit('.py', 1)[0]
            module = importlib.import_module('.' + tool, __name__)
            self.available_tools[tool] = getattr(module, tool)
    
    @abstractmethod
    def describe_tools(self) -> str:
        raise NotImplementedError
    
    @abstractmethod
    def parse_tool(self, text, loop: Optional[asyncio.AbstractEventLoop] = None) -> tuple[str, str] | tuple[None, None]:
        """
        Parse and execute a tool.

        Args:
            text: Tool call.
                For llama, str containing: "<|start_tool|>tool(args)<|end_tool|>"
                For openai, dict of their function call format

            loop: The running asyncio tool to execute async tools in.
                  If not provided, a new loop will be created and ran.
        
        Returns:
            tuple of:
                [0] - the tool call itself ("tool(args)")
                [1] - the result of the tool as string, or the summary of an exception that occurred
            or tuple of (None, None) if text doesn't contain a tool call
        
        Notes:
            Thread creation is the responsibility of the caller.
            A tool can be either sync or async.
        """
        raise NotImplementedError

    def _run_tool(self, target: Callable, args: tuple, kwargs: dict, loop: Optional[asyncio.AbstractEventLoop]):
        if inspect.iscoroutinefunction(target):
            if not loop:
                loop = asyncio.new_event_loop()
            if not loop.is_running():
                return loop.run_until_complete(target(*args, **kwargs))
            else:
                future = asyncio.run_coroutine_threadsafe(target(*args, **kwargs), loop)
                return future.result()
        else:
            return target(*args, **kwargs)


class LlamaToolsManager(ToolsManager):
    def describe_tools(self) -> str:
        tools = []
        for tool in self.available_tools.values():
            name = tool.__name__
            sig = inspect.signature(tool)
            params = []
            for param in sig.parameters.values():
                params.append(param.replace(default=inspect.Parameter.empty))
            sig = sig.replace(parameters=params, return_annotation=inspect.Signature.empty)
            doc = inspect.getdoc(tool) or "No description available"
            tools.append(f"{name}{sig} - {doc}")
        return "\n".join(tools)
    
    def parse_tool(self, text: str, loop: asyncio.AbstractEventLoop | None = None) -> tuple[str, str] | tuple[None, None]:
        idx = text.find('<|start_tool|>')
        if idx == -1:
            return None, None
        idx += len('<|start_tool|>')
        idx2 = text.find('<|end_tool|>', idx)
        if idx2 == -1:
            idx2 = None
        
        tool = text[idx:idx2]
        if not tool:
            return None, None
        try:
            ret = self._parse_tool(tool, loop)
        except Exception as e:
            print(f"Exception while calling tool {tool}:")
            print(format_exc())
            return tool, f"Error: {str(e).split('\n')[-1]}"
        return tool, str(ret)
    
    def _parse_tool(self, tool: str, loop: Optional[asyncio.AbstractEventLoop]):
        tree = ast.parse(tool, mode='eval')

        # validation
        if not isinstance(tree.body, ast.Call):
            raise TypeError(f"Invalid body: {type(tree.body).__name__}")
        if not isinstance(tree.body.func, ast.Name):
            raise TypeError(f"Invalid body.func: {type(tree.body.func).__name__}")
        if not tree.body.func.id in self.available_tools:
            raise ValueError(f"Unknown tool: {tree.body.func.id}")
        for node in tree.body.args:
            if not isinstance(node, ast.Constant):
                raise ValueError(f"Invalid body.args: {type(node).__name__}")
        for node in tree.body.keywords:
            if not isinstance(node.value, ast.Constant):
                raise ValueError(f"Invalid body.keywords: {type(node.value).__name__}")
        
        target = self.available_tools[tree.body.func.id]
        args = tuple(x.value for x in tree.body.args)
        kwargs = {x.arg: x.value.value for x in tree.body.keywords}
        return self._run_tool(target, args, kwargs, loop)

