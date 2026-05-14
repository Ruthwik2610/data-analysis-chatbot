import os
import json
import logging
from e2b_code_interpreter import Sandbox
from typing import Any, Dict

logger = logging.getLogger(__name__)

class CodeSandbox:
    def __init__(self):
        self.sandbox = None

    def __enter__(self):
        self.sandbox = Sandbox()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.sandbox:
            self.sandbox.close()

    def run_python(self, code: str) -> Dict[str, Any]:
        if not self.sandbox:
            raise RuntimeError("Sandbox not initialized. Use 'with CodeSandbox() as sandbox:'")
        
        try:
            execution = self.sandbox.run_code(code)
            
            results = []
            if execution.results:
                for result in execution.results:
                    if result.is_main_result:
                        results.append({"type": "main", "data": result.text})
                    elif result.png:
                        results.append({"type": "image/png", "data": result.png})
                    elif result.text:
                        results.append({"type": "text", "data": result.text})

            return {
                "success": not execution.error,
                "output": execution.text,
                "error": execution.error.value if execution.error else None,
                "traceback": execution.error.traceback if execution.error else None,
                "results": results
            }
        except Exception as e:
            logger.error(f"Error executing python code in sandbox: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "traceback": None,
                "results": []
            }
