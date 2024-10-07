import os
import ast
import inspect
import asyncio
import importlib
import importlib.util
from threading import Thread
from queue import Queue
from typing import Callable, Optional

class ToolsManager:
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
    
    def parse_tool(self, text: str, loop: Optional[asyncio.AbstractEventLoop] = None) -> tuple[str, str]:
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

        is_async = inspect.iscoroutinefunction(target)
        if is_async and not loop:
            loop = asyncio.new_event_loop()
        q = Queue()
        exc = Queue()
        if is_async:
            p = Thread(target=_run_async, args=(loop, q, exc, target)+args, kwargs=kwargs)
        else:
            p = Thread(target=_run, args=(q, exc, target)+args, kwargs=kwargs)
        p.start()
        p.join()
        if not exc.empty():
            raise exc.get()
        return q.get()

def _run(result: Queue, exception: Queue, target: Callable, *args, **kwargs):
    try:
        ret = target(*args, **kwargs)
    except Exception as e:
        exception.put(e)
    else:
        result.put(ret)
def _run_async(loop: asyncio.AbstractEventLoop, result: Queue, exception: Queue, target: Callable, *args, **kwargs):
    try:
        if not loop.is_running():
            ret = loop.run_until_complete(target(*args, **kwargs))
        else:
            future = asyncio.run_coroutine_threadsafe(target(*args, **kwargs), loop)
            ret = future.result()
    except Exception as e:
        exception.put(e)
    else:
        result.put(ret)