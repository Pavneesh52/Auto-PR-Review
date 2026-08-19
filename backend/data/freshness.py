from typing: Dict, Any, List
from backend.database.postgres import AsyncSessionLocal
from backend.database.repository import RepoFileIndexRepository
from backend.integrations.github_client import github_client
from backend.memory.context_retriever import ContextRetriever
from backend.observability import get_logger

logger = get_logger(__name__)


class FreshnessTracker:
    def __init__(self):
        pass

    async def check_and_update_freshness(
        self,
        installation_id: int,
        repo_full_name: str,
        ref: str = "main",
    ) -> Dict[str, Any]:
        async with AsyncSessionLocal() as session:
            file_index_repo = RepoFileIndexRepository(session)
            retriever = ContextRetriever(session)
            
            indexed_files = await file_index_repo.list_repo_files(repo_full_name)
            
            current_files = await self._get_current_files(installation_id, repo_full_name, ref)
            
            updated = 0
            new_files = 0
            
            for file_path, sha in current_files.items():
                indexed = next((f for f in indexed_files if f.path == file_path), None)
                
                if indexed is None:
                    new_files += 1
                    file_content = await github_client.get_file_content(
                        installation_id, repo_full_name, file_path, ref
                    )
                    if file_content:
                        chunks = retriever.embedder.chunk_text(file_content)
                        chunk_data = []
                        for i, chunk_text in enumerate(chunks):
                            embedding = await retriever.embedder.embed(chunk_text)
                            chunk_data.append({
                                "path": file_path,
                                "symbol": retriever._extract_symbol(chunk_text),
                                "chunk_index": i,
                                "content": chunk_text,
                                "embedding": embedding,
                                "token_count": retriever.embedder.count_tokens(chunk_text),
                            })
                        await retriever.tiger_client.upsert_chunks(repo_full_name, chunk_data)
                        await retriever.tiger_client.upsert_file_index(repo_full_name, file_path, sha, len(chunks))
                elif indexed.sha != sha:
                    updated += 1
                    file_content = await github_client.get_file_content(
                        installation_id, repo_full_name, file_path, ref
                    )
                    if file_content:
                        chunks = retriever.embedder.chunk_text(file_content)
                        chunk_data = []
                        for i, chunk_text in enumerate(chunks):
                            embedding = await retriever.embedder.embed(chunk_text)
                            chunk_data.append({
                                "path": file_path,
                                "symbol": retriever._extract_symbol(chunk_text),
                                "chunk_index": i,
                                "content": chunk_text,
                                "embedding": embedding,
                                "token_count": retriever.embedder.count_tokens(chunk_text),
                            })
                        await retriever.tiger_client.upsert_chunks(repo_full_name, chunk_data)
                        await retriever.tiger_client.upsert_file_index(repo_full_name, file_path, sha, len(chunks))
            
            logger.info("freshness_check_completed", repo=repo_full_name, updated=updated, new_files=new_files)
            
            return {
                "repo": repo_full_name,
                "updated_files": updated,
                "new_files": new_files,
                "total_indexed": len(indexed_files) + new_files - updated,
            }

    async def _get_current_files(
        self,
        installation_id: int,
        repo_full_name: str,
        ref: str,
    ) -> Dict[str, str]:
        files = {}
        
        try:
            client = github_client.get_installation_client(installation_id)
            repo = client.get_repo(repo_full_name)
            
            contents = repo.get_contents("", ref=ref)
            
            while contents:
                content = contents.pop(0)
                if content.type == "dir":
                    contents.extend(repo.get_contents(content.path, ref=ref))
                elif content.type == "file" and self._is_code_file(content.path):
                    files[content.path] = content.sha
        except Exception as e:
            logger.error("file_list_failed", repo=repo_full_name, error=str(e))
        
        return files

    def _is_code_file(self, path: str) -> bool:
        code_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
            ".cpp", ".cc", ".c", ".h", ".hpp", ".cs", ".rb", ".php",
            ".swift", ".kt", ".scala", ".clj", ".hs", ".ml", ".fs",
        }
        return any(path.endswith(ext) for ext in code_extensions)


async def check_repository_freshness(installation_id: int, repo_full_name: str, ref: str = "main") -> Dict[str, Any]:
    tracker = FreshnessTracker()
    return await tracker.check_and_update_freshness(installation_id, repo_full_name, ref)