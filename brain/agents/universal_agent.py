"""
brain/agents/universal_agent.py
Ultra-Advanced Agent: Uses Gemini native function calling to interact with the system, browser, and UI.
"""

import json
from config.logger import get_logger

log = get_logger("universal_agent")

class UniversalAgent:
    def __init__(self, ai_client, brain):
        self.ai = ai_client
        self.brain = brain
        self.playwright = None
        self.computer = None
        self.sandbox = None
        self.rag_manager = None
        self._init_tools()

    def _init_tools(self):
        try:
            from tools.web.playwright_agent import PlaywrightController
            self.playwright = PlaywrightController()
        except Exception as e:
            log.warning(f"Failed to load PlaywrightController: {e}")
        try:
            from tools.system.computer_use import ComputerController
            self.computer = ComputerController()
        except Exception as e:
            log.warning(f"Failed to load ComputerController: {e}")
        try:
            from tools.execution.code_sandbox import CodeSandbox
            self.sandbox = CodeSandbox()
        except Exception as e:
            log.warning(f"Failed to load CodeSandbox: {e}")
        try:
            from memory.rag_manager import RAGManager
            self.rag_manager = RAGManager()
        except Exception as e:
            log.warning(f"Failed to load RAGManager: {e}")

    def get_tool_declarations(self):
        """Returns the function schemas for Gemini tool calling."""
        tools = [
            {
                "name": "run_system_action",
                "description": "Run a standard Jarvis command like 'open chrome', 'volume up', or 'search youtube'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The command to run"}
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "browser_go_to",
                "description": "Open a headless browser and navigate to a URL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to navigate to"}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "browser_extract_text",
                "description": "Extract text from the current page in the headless browser.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector to extract text from, defaults to body"}
                    },
                    "required": ["selector"]
                }
            },
            {
                "name": "computer_type_text",
                "description": "Type text directly using the physical keyboard via PyAutoGUI.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to type"}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "computer_press_key",
                "description": "Press a single key like 'enter', 'tab', 'esc'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Key to press"}
                    },
                    "required": ["key"]
                }
            },
            {
                "name": "python_execute",
                "description": "Execute arbitrary Python code in a local sandbox to solve data, math, or automation tasks. You can use standard libraries and pandas/numpy/matplotlib. Returns stdout/stderr.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "The raw Python code string to execute."}
                    },
                    "required": ["code"]
                }
            },
            {
                "name": "memory_ingest_file",
                "description": "Ingest a document (.txt, .md, .pdf) into Jarvis's long-term memory Knowledge Base.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filepath": {"type": "string", "description": "Absolute path to the file"}
                    },
                    "required": ["filepath"]
                }
            },
            {
                "name": "memory_search",
                "description": "Search Jarvis's long-term memory for information using semantic search.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"}
                    },
                    "required": ["query"]
                }
            }
        ]
        return tools

    def execute_tool(self, tool_name: str, kwargs: dict) -> str:
        """Executes the mapped tool and returns the result as string."""
        log.info(f"Executing tool {tool_name} with args {kwargs}")
        try:
            if tool_name == "run_system_action":
                res = self.brain.process(kwargs["command"])
                return f"Success: {res}"
            elif tool_name == "browser_go_to":
                if not self.playwright: return "Browser tool unavailable."
                return self.playwright.go_to(kwargs["url"])
            elif tool_name == "browser_extract_text":
                if not self.playwright: return "Browser tool unavailable."
                return self.playwright.extract_text(kwargs.get("selector", "body"))
            elif tool_name == "computer_type_text":
                if not self.computer: return "Computer tool unavailable."
                return self.computer.type_text(kwargs["text"])
            elif tool_name == "computer_press_key":
                if not self.computer: return "Computer tool unavailable."
                return self.computer.press_key(kwargs["key"])
            elif tool_name == "python_execute":
                if not self.sandbox: return "Code Sandbox unavailable."
                return self.sandbox.execute_python(kwargs["code"])
            elif tool_name == "memory_ingest_file":
                if not self.rag_manager: return "RAG Memory unavailable."
                return self.rag_manager.ingest_file(kwargs["filepath"])
            elif tool_name == "memory_search":
                if not self.rag_manager: return "RAG Memory unavailable."
                return self.rag_manager.search(kwargs["query"])
            else:
                return f"Unknown tool: {tool_name}"
        except Exception as e:
            log.error(f"Tool {tool_name} failed: {e}")
            return f"Error executing {tool_name}: {e}"

    def run(self, task: str) -> str:
        """Run the universal agent loop with the prompt and tool calling."""
        if self.ai.provider != "gemini":
            return self.ai.chat(task) # Fallback if not gemini
        
        from google.genai import types
        
        system_instruction = (
            "You are an ultra-advanced autonomous agent. You have access to tools that can control the computer, "
            "interact with the browser natively, run system commands, and dynamically WRITE and EXECUTE Python code. "
            "You also have a long-term RAG memory to search for documents or past context using memory_search. "
            "Think step-by-step. If you need information, use the browser tools or memory_search. "
            "If you need to calculate something, analyze data, or generate a graph, use python_execute. "
            "If you write Python code and the python_execute tool returns an error or traceback, YOU MUST auto-debug it. "
            "Read the error, figure out what went wrong, rewrite the code, and call python_execute again until it succeeds. "
            "If you need to control the UI natively, use the computer tools. "
            "When the task is complete, return a final summary of what you did."
        )

        try:
            # We construct a tool config manually
            tool_declarations = [{"function_declarations": self.get_tool_declarations()}]
            
            # Start chat session
            chat = self.ai.client.chats.create(
                model=self.ai._gemini_models()[0],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tool_declarations,
                    temperature=0.2
                )
            )
            
            response = chat.send_message(task)
            
            # Maximum 10 turns to prevent infinite loop
            for _ in range(10):
                if response.function_calls:
                    for function_call in response.function_calls:
                        tool_name = function_call.name
                        kwargs = {k: v for k, v in function_call.args.items()}
                        result = self.execute_tool(tool_name, kwargs)
                        
                        # Send tool result back to model
                        response = chat.send_message(
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_function_response(
                                        name=tool_name,
                                        response={"result": result}
                                    )
                                ]
                            )
                        )
                else:
                    return response.text
                    
            return "Agent reached maximum iterations without finishing."
            
        except Exception as e:
            log.error(f"Universal Agent failed: {e}")
            return f"Agent failed: {str(e)}"
