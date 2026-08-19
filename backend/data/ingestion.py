from typing: Dict, List, Any
from backend.integrations.github_client import github_client
from backend.memory.context_retriever import ContextRetriever
from backend.database.postgres import AsyncSessionLocal
from backend.observability import get_logger

logger = get_logger(__name__)


class RepositoryIngestion:
    def __init__(self):
        pass

    async def ingest_repository(
        self,
        installation_id: int,
        repo_full_name: str,
        ref: str = "main",
    ) -> Dict[str, Any]:
        async with AsyncSessionLocal() as session:
            retriever = ContextRetriever(session)
            
            files = await self._get_repository_files(installation_id, repo_full_name, ref)
            
            if not files:
                return {"status": "no_files", "repo": repo_full_name}
            
            total_chunks = await retriever.index_repository(repo_full_name, files)
            
            logger.info("repository_ingested", repo=repo_full_name, files=len(files), chunks=total_chunks)
            
            return {
                "status": "completed",
                "repo": repo_full_name,
                "files_indexed": len(files),
                "total_chunks": total_chunks,
            }

    async def _get_repository_files(
        self,
        installation_id: int,
        repo_full_name: str,
        ref: str,
    ) -> Dict[str, str]:
        files = {}
        
        try:
            from github import Github
            client = github_client.get_installation_client(installation_id)
            repo = client.get_repo(repo_full_name)
            
            contents = repo.get_contents("", ref=ref)
            
            while contents:
                content = contents.pop(0)
                if content.type == "dir":
                    contents.extend(repo.get_contents(content.path, ref=ref))
                elif content.type == "file" and self._is_code_file(content.path):
                    file_content = await github_client.get_file_content(
                        installation_id, repo_full_name, content.path, ref
                    )
                    if file_content:
                        files[content.path] = file_content
        except Exception as e:
            logger.error("file_retrieval_failed", repo=repo_full_name, error=str(e))
        
        return files

    def _is_code_file(self, path: str) -> bool:
        code_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
            ".cpp", ".cc", ".c", ".h", ".hpp", ".cs", ".rb", ".php",
            ".swift", ".kt", ".scala", ".clj", ".hs", ".ml", ".fs",
        }
        return any(path.endswith(ext) for ext in code_extensions)


async def ingest_repository(installation_id: int, repo_full_name: str, ref: str = "main") -> Dict[str, Any]:
    ingestion = RepositoryIngestion()
    return await ingestion.ingest_repository(installation_id, repo_full_name, ref)