import docker
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class SandboxResult:
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0


class DockerSandbox:
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.available = True
        except Exception:
            self.client = None
            self.available = False

    async def run_code(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        if not self.available:
            return SandboxResult(
                success=False,
                output="",
                error="Docker not available",
                exit_code=-1,
            )

        image_map = {
            "python": "python:3.12-slim",
            "javascript": "node:20-slim",
            "typescript": "node:20-slim",
        }
        
        image = image_map.get(language, "python:3.12-slim")
        command_map = {
            "python": ["python", "-c"],
            "javascript": ["node", "-e"],
            "typescript": ["npx", "ts-node", "-e"],
        }
        command = command_map.get(language, ["python", "-c"])

        try:
            container = await asyncio.to_thread(
                self.client.containers.run,
                image,
                command + [code],
                detach=True,
                remove=True,
                environment=env or {},
                mem_limit="256m",
                cpu_quota=50000,
                network_disabled=True,
            )
            
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(container.wait, timeout=timeout),
                    timeout=timeout + 5,
                )
                logs = await asyncio.to_thread(container.logs, stdout=True, stderr=True)
                output = logs.decode("utf-8") if isinstance(logs, bytes) else logs
                
                return SandboxResult(
                    success=result["StatusCode"] == 0,
                    output=output,
                    exit_code=result["StatusCode"],
                )
            except asyncio.TimeoutError:
                try:
                    container.kill()
                except Exception:
                    pass
                return SandboxResult(
                    success=False,
                    output="",
                    error="Execution timeout",
                    exit_code=-1,
                )
        
        except Exception as e:
            return SandboxResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
            )


sandbox = DockerSandbox()