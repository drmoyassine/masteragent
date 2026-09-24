"""
Storage Service Module - Abstract interface and implementations for prompt storage.

Supports two storage modes:
- GitHub: Store prompts in a GitHub repository (cloud sync, collaboration)
- Local: Store prompts in local filesystem (no external dependencies)
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from pathlib import Path
from core.safe_paths import safe_join, validate_relative_storage_path, validate_storage_component
import json
import os
import base64
import httpx
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Import shared DB utilities from core package (single source of truth)
from core.db import get_db_context, get_github_settings

ROOT_DIR = Path(__file__).parent
LOCAL_STORAGE_PATH = ROOT_DIR / "local_prompts"



def get_storage_mode(user_id: str) -> str:
    """Get the storage mode for a user. Defaults to 'local' for new users."""
    settings = get_github_settings(user_id)
    if settings:
        return settings.get("storage_mode", "local")
    return "local"


class StorageService(ABC):
    """Abstract base class for prompt storage services."""
    
    @abstractmethod
    async def create_prompt(
        self, 
        folder_path: str, 
        name: str, 
        description: str,
        sections: List[Dict],
        variables: Dict
    ) -> bool:
        """Create a new prompt with manifest and sections."""
        pass
    
    @abstractmethod
    async def get_prompt_content(self, folder_path: str, version: str = "v1") -> Optional[Dict]:
        """Get prompt content including manifest and sections."""
        pass
    
    @abstractmethod
    async def get_section(self, folder_path: str, filename: str, version: str = "v1") -> Optional[Dict]:
        """Get a specific section file."""
        pass
    
    @abstractmethod
    async def create_section(
        self, 
        folder_path: str, 
        filename: str, 
        content: str,
        version: str = "v1"
    ) -> bool:
        """Create a new section file."""
        pass
    
    @abstractmethod
    async def update_section(
        self, 
        folder_path: str, 
        filename: str, 
        content: str,
        version: str = "v1"
    ) -> bool:
        """Update an existing section file."""
        pass
    
    @abstractmethod
    async def delete_section(
        self, 
        folder_path: str, 
        filename: str,
        version: str = "v1"
    ) -> bool:
        """Delete a section file."""
        pass
    
    @abstractmethod
    async def update_manifest(
        self, 
        folder_path: str, 
        manifest: Dict,
        version: str = "v1"
    ) -> bool:
        """Update the manifest file."""
        pass
    
    @abstractmethod
    async def delete_prompt(self, folder_path: str) -> bool:
        """Delete all files for a prompt."""
        pass
    
    @abstractmethod
    async def list_prompts(self) -> List[Dict]:
        """List all prompts in storage."""
        pass
    
    async def render_prompt(
        self, 
        folder_path: str, 
        version: str,
        variables: Dict
    ) -> str:
        """Render a prompt with variables substituted."""
        content = await self.get_prompt_content(folder_path, version)
        if not content:
            return ""
        
        # Combine all sections
        rendered = []
        for section in content.get("sections", []):
            section_content = section.get("content", "")
            # Substitute variables
            for var_name, var_value in variables.items():
                section_content = section_content.replace(f"{{{{{var_name}}}}}", str(var_value))
            rendered.append(section_content)
        
        return "\n\n".join(rendered)


class GitHubStorageService(StorageService):
    """Storage service that uses GitHub repository for prompt storage."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.settings = get_github_settings(user_id)

    @staticmethod
    def _version_path(folder_path: str, version: str) -> str:
        folder = validate_relative_storage_path(folder_path, "prompt path")
        return f"{folder}/{validate_storage_component(version, 'version')}"
        
    def _get_repo_info(self) -> tuple:
        """Get repository owner and name from settings."""
        if not self.settings:
            raise ValueError("GitHub not configured")
        return (
            self.settings.get("github_owner"),
            self.settings.get("github_repo")
        )
    
    async def _github_api_request(
        self, 
        method: str, 
        endpoint: str, 
        data: dict = None
    ) -> Any:
        """Make authenticated request to GitHub API."""
        if not self.settings or not self.settings.get("github_token"):
            raise ValueError("GitHub not configured")
        
        owner, repo = self._get_repo_info()
        url = f"https://api.github.com/repos/{owner}/{repo}{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {self.settings['github_token']}", # Switched to Bearer
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, headers=headers)
            elif method == "PUT":
                response = await client.put(url, headers=headers, json=data)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code in [200, 201]:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                raise Exception(f"GitHub API error: {response.status_code} - {response.text}")
    
    async def create_prompt(
        self, 
        folder_path: str, 
        name: str, 
        description: str,
        sections: List[Dict],
        variables: Dict
    ) -> bool:
        """Create a new prompt in GitHub."""
        version_path = self._version_path(folder_path, "v1")
        
        # Create manifest
        manifest = {
            "prompt_id": name.lower().replace(" ", "-"),
            "name": name,
            "description": description,
            "version": "v1",
            "sections": [],
            "variables": variables
        }
        
        manifest_content = base64.b64encode(
            json.dumps(manifest, indent=2).encode()
        ).decode()
        
        await self._github_api_request("PUT", f"/contents/{version_path}/manifest.json", {
            "message": f"Create prompt: {name}",
            "content": manifest_content
        })
        
        # Create sections
        for section in sections:
            filename = section.get("filename", f"{section.get('order', 1):02d}_{section.get('name', 'section')}.md")
            content = base64.b64encode(section.get("content", "").encode()).decode()
            
            await self._github_api_request("PUT", f"/contents/{version_path}/{filename}", {
                "message": f"Add section: {filename}",
                "content": content
            })
            
            manifest["sections"].append(filename)
        
        # Update manifest with section list
        if sections:
            manifest_response = await self._github_api_request(
                "GET", f"/contents/{version_path}/manifest.json"
            )
            if manifest_response:
                manifest_content = base64.b64encode(
                    json.dumps(manifest, indent=2).encode()
                ).decode()
                await self._github_api_request("PUT", f"/contents/{version_path}/manifest.json", {
                    "message": "Update manifest with sections",
                    "content": manifest_content,
                    "sha": manifest_response["sha"]
                })
        
        return True
    
    async def get_prompt_content(self, folder_path: str, version: str = "v1") -> Optional[Dict]:
        """Get prompt content from GitHub."""
        version_path = self._version_path(folder_path, version)
        
        # Get manifest
        manifest_data = await self._github_api_request(
            "GET", f"/contents/{version_path}/manifest.json"
        )
        if not manifest_data:
            return None
        
        manifest = json.loads(
            base64.b64decode(manifest_data["content"]).decode()
        )
        
        # Get sections
        sections = []
        for section_file in manifest.get("sections", []):
            validate_storage_component(section_file, "section filename")
            section_data = await self._github_api_request(
                "GET", f"/contents/{version_path}/{section_file}"
            )
            if section_data:
                sections.append({
                    "filename": section_file,
                    "content": base64.b64decode(section_data["content"]).decode(),
                    "sha": section_data.get("sha")
                })
        
        return {
            "manifest": manifest,
            "sections": sections,
            "sha": manifest_data.get("sha")
        }
    
    async def get_section(self, folder_path: str, filename: str, version: str = "v1") -> Optional[Dict]:
        """Get a specific section from GitHub."""
        version_path = self._version_path(folder_path, version)
        validate_storage_component(filename, "section filename")
        section_data = await self._github_api_request(
            "GET", f"/contents/{version_path}/{filename}"
        )
        
        if not section_data:
            return None
        
        return {
            "filename": filename,
            "content": base64.b64decode(section_data["content"]).decode(),
            "sha": section_data.get("sha")
        }
    
    async def create_section(
        self, 
        folder_path: str, 
        filename: str, 
        content: str,
        version: str = "v1"
    ) -> bool:
        """Create a new section in GitHub."""
        version_path = self._version_path(folder_path, version)
        validate_storage_component(filename, "section filename")
        encoded_content = base64.b64encode(content.encode()).decode()
        
        await self._github_api_request("PUT", f"/contents/{version_path}/{filename}", {
            "message": f"Add section: {filename}",
            "content": encoded_content
        })
        return True
    
    async def update_section(
        self, 
        folder_path: str, 
        filename: str, 
        content: str,
        version: str = "v1"
    ) -> bool:
        """Update a section in GitHub."""
        version_path = self._version_path(folder_path, version)
        validate_storage_component(filename, "section filename")
        
        # Get current file SHA
        current = await self._github_api_request(
            "GET", f"/contents/{version_path}/{filename}"
        )
        if not current:
            return False
        
        encoded_content = base64.b64encode(content.encode()).decode()
        
        await self._github_api_request("PUT", f"/contents/{version_path}/{filename}", {
            "message": f"Update section: {filename}",
            "content": encoded_content,
            "sha": current["sha"]
        })
        return True
    
    async def delete_section(
        self, 
        folder_path: str, 
        filename: str,
        version: str = "v1"
    ) -> bool:
        """Delete a section from GitHub."""
        version_path = self._version_path(folder_path, version)
        validate_storage_component(filename, "section filename")
        
        # Get current file SHA
        current = await self._github_api_request(
            "GET", f"/contents/{version_path}/{filename}"
        )
        if not current:
            return False
        
        await self._github_api_request("DELETE", f"/contents/{version_path}/{filename}", {
            "message": f"Delete section: {filename}",
            "sha": current["sha"]
        })
        return True
    
    async def update_manifest(
        self, 
        folder_path: str, 
        manifest: Dict,
        version: str = "v1"
    ) -> bool:
        """Update manifest in GitHub."""
        version_path = self._version_path(folder_path, version)
        
        # Get current manifest SHA
        current = await self._github_api_request(
            "GET", f"/contents/{version_path}/manifest.json"
        )
        if not current:
            return False
        
        encoded_content = base64.b64encode(
            json.dumps(manifest, indent=2).encode()
        ).decode()
        
        await self._github_api_request("PUT", f"/contents/{version_path}/manifest.json", {
            "message": "Update manifest",
            "content": encoded_content,
            "sha": current["sha"]
        })
        return True
    
    async def delete_prompt(self, folder_path: str) -> bool:
        """Delete prompt from GitHub (deletes all files recursively)."""
        # GitHub doesn't have a recursive delete, so we need to delete each file
        # This is a simplified version - in production you'd want to handle all versions
        try:
            # Get all contents
            folder_path = validate_relative_storage_path(folder_path, "prompt path")
            contents = await self._github_api_request("GET", f"/contents/{folder_path}")
            if not contents:
                return True
            
            # Delete each item recursively
            for item in contents:
                if item["type"] == "dir":
                    # Recursively delete directory contents
                    await self.delete_prompt(item["path"])
                else:
                    await self._github_api_request("DELETE", f"/contents/{item['path']}", {
                        "message": f"Delete file: {item['path']}",
                        "sha": item["sha"]
                    })
            
            return True
        except Exception as e:
            print(f"Error deleting prompt from GitHub: {e}")
            return False
    
    async def list_prompts(self) -> List[Dict]:
        """List all prompts in GitHub repo."""
        try:
            contents = await self._github_api_request("GET", "/contents/prompts")
            if not contents:
                return []
            
            prompts = []
            for item in contents:
                if item["type"] == "dir":
                    prompts.append({
                        "name": item["name"],
                        "path": item["path"]
                    })
            return prompts
        except Exception as e:
            logger.error(f"Failed to list GitHub prompts: {e}")
            return []


class LocalStorageService(StorageService):
    """Storage service that uses local filesystem for prompt storage."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.storage_path = LOCAL_STORAGE_PATH / user_id
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def _get_prompt_path(self, folder_path: str, version: str = "v1") -> Path:
        """Get the filesystem path for a prompt version."""
        folder = validate_relative_storage_path(folder_path, "prompt path")
        version = validate_storage_component(version, "version")
        return safe_join(self.storage_path, folder, version)
    
    async def create_prompt(
        self, 
        folder_path: str, 
        name: str, 
        description: str,
        sections: List[Dict],
        variables: Dict
    ) -> bool:
        """Create a new prompt locally."""
        version_path = self._get_prompt_path(folder_path)
        version_path.mkdir(parents=True, exist_ok=True)
        
        # Create manifest
        manifest = {
            "prompt_id": name.lower().replace(" ", "-"),
            "name": name,
            "description": description,
            "version": "v1",
            "sections": [],
            "variables": variables,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Create sections and update manifest
        for section in sections:
            filename = section.get("filename", f"{section.get('order', 1):02d}_{section.get('name', 'section')}.md")
            validate_storage_component(filename, "section filename")
            section_path = version_path / filename
            
            with open(section_path, "w", encoding="utf-8") as f:
                f.write(section.get("content", ""))
            
            manifest["sections"].append(filename)
        
        # Write manifest
        manifest_path = version_path / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        
        return True
    
    async def get_prompt_content(self, folder_path: str, version: str = "v1") -> Optional[Dict]:
        """Get prompt content from local filesystem."""
        version_path = self._get_prompt_path(folder_path, version)
        manifest_path = version_path / "manifest.json"
        
        if not manifest_path.exists():
            return None
        
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        # Get sections
        sections = []
        for section_file in manifest.get("sections", []):
            validate_storage_component(section_file, "section filename")
            section_path = version_path / section_file
            if section_path.exists():
                with open(section_path, "r", encoding="utf-8") as f:
                    sections.append({
                        "filename": section_file,
                        "content": f.read()
                    })
        
        return {
            "manifest": manifest,
            "sections": sections
        }
    
    async def get_section(self, folder_path: str, filename: str, version: str = "v1") -> Optional[Dict]:
        """Get a specific section from local filesystem."""
        version_path = self._get_prompt_path(folder_path, version)
        validate_storage_component(filename, "section filename")
        section_path = version_path / filename
        
        if not section_path.exists():
            return None
        
        with open(section_path, "r", encoding="utf-8") as f:
            return {
                "filename": filename,
                "content": f.read()
            }
    
    async def create_section(
        self, 
        folder_path: str, 
        filename: str, 
        content: str,
        version: str = "v1"
    ) -> bool:
        """Create a new section locally."""
        version_path = self._get_prompt_path(folder_path, version)
        validate_storage_component(filename, "section filename")
        version_path.mkdir(parents=True, exist_ok=True)
        
        section_path = version_path / filename
        with open(section_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return True
    
    async def update_section(
        self, 
        folder_path: str, 
        filename: str, 
        content: str,
        version: str = "v1"
    ) -> bool:
        """Update a section locally."""
        version_path = self._get_prompt_path(folder_path, version)
        validate_storage_component(filename, "section filename")
        section_path = version_path / filename
        
        if not section_path.exists():
            return False
        
        with open(section_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Update manifest updated_at
        manifest_path = version_path / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        
        return True
    
    async def delete_section(
        self, 
        folder_path: str, 
        filename: str,
        version: str = "v1"
    ) -> bool:
        """Delete a section locally."""
        version_path = self._get_prompt_path(folder_path, version)
        validate_storage_component(filename, "section filename")
        section_path = version_path / filename
        
        if not section_path.exists():
            return False
        
        section_path.unlink()
        return True
    
    async def update_manifest(
        self, 
        folder_path: str, 
        manifest: Dict,
        version: str = "v1"
    ) -> bool:
        """Update manifest locally."""
        version_path = self._get_prompt_path(folder_path, version)
        manifest_path = version_path / "manifest.json"
        
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        
        return True
    
    async def delete_prompt(self, folder_path: str) -> bool:
        """Delete prompt from local filesystem."""
        folder = validate_relative_storage_path(folder_path, "prompt path")
        prompt_path = safe_join(self.storage_path, folder)
        
        if not prompt_path.exists():
            return False
        
        import shutil
        shutil.rmtree(prompt_path)
        return True
    
    async def list_prompts(self) -> List[Dict]:
        """List all prompts in local storage."""
        prompts_path = self.storage_path / "prompts"
        
        if not prompts_path.exists():
            return []
        
        prompts = []
        for item in prompts_path.iterdir():
            if item.is_dir():
                prompts.append({
                    "name": item.name,
                    "path": str(item.relative_to(self.storage_path))
                })
        
        return prompts


class DatabaseStorageService(StorageService):
    """Zero-git prompt storage: sections and manifests live as Postgres rows.

    Implements the same file semantics as the filesystem backends — every
    "file" (manifest.json, NN_section.md) is a row keyed by
    (folder_path, version, filename) — so the editor routes and the pipeline
    resolver work unchanged. Versioning stays append-only: creating a version
    copies rows into the new version; nothing is mutated in place by
    versioning, so any version remains a complete, restorable snapshot
    (lightweight-prompt-engine design, docs/plans/lightweight-prompt-engine-design.md).
    """

    def __init__(self, user_id: str = None):
        self.user_id = user_id

    async def _write_file(self, folder_path: str, version: str, filename: str, content: str) -> None:
        validate_storage_component(filename, "section filename")
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO pm_files (folder_path, version, filename, content, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (folder_path, version, filename)
                DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                """,
                (folder_path, version, filename, content),
            )

    async def create_prompt(
        self,
        folder_path: str,
        name: str,
        description: str,
        sections: List[Dict],
        variables: Dict,
    ) -> bool:
        manifest = {
            "prompt_id": name.lower().replace(" ", "-"),
            "name": name,
            "description": description,
            "version": "v1",
            "sections": [],
            "variables": variables or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Replace any prior content for this folder (fresh prompt creation).
        await self.delete_prompt(folder_path)
        for section in sections:
            filename = section.get("filename", f"{section.get('order', 1):02d}_{section.get('name', 'section')}.md")
            manifest["sections"].append(filename)
            await self._write_file(folder_path, "v1", filename, section.get("content", ""))
        await self._write_file(folder_path, "v1", "manifest.json", json.dumps(manifest, indent=2))
        return True

    async def get_prompt_content(self, folder_path: str, version: str = "v1") -> Optional[Dict]:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT filename, content FROM pm_files WHERE folder_path = %s AND version = %s ORDER BY filename ASC",
                (folder_path, version),
            )
            rows = [dict(r) for r in cursor.fetchall()]
        if not rows:
            return None
        manifest: Dict[str, Any] = {}
        by_name = {r["filename"]: r["content"] for r in rows}
        if "manifest.json" in by_name:
            try:
                manifest = json.loads(by_name["manifest.json"])
            except Exception:
                manifest = {}
        names = manifest.get("sections") or [r["filename"] for r in rows if r["filename"] != "manifest.json"]
        sections = [{"filename": n, "content": by_name[n]} for n in names if n in by_name]
        return {"manifest": manifest, "sections": sections}

    async def get_section(self, folder_path: str, filename: str, version: str = "v1") -> Optional[Dict]:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content FROM pm_files WHERE folder_path = %s AND version = %s AND filename = %s",
                (folder_path, version, filename),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {"filename": filename, "content": row["content"]}

    async def create_section(self, folder_path: str, filename: str, content: str, version: str = "v1") -> bool:
        await self._write_file(folder_path, version, filename, content)
        return True

    async def update_section(self, folder_path: str, filename: str, content: str, version: str = "v1") -> bool:
        await self._write_file(folder_path, version, filename, content)
        return True

    async def delete_section(self, folder_path: str, filename: str, version: str = "v1") -> bool:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM pm_files WHERE folder_path = %s AND version = %s AND filename = %s",
                (folder_path, version, filename),
            )
        return True

    async def update_manifest(self, folder_path: str, manifest: Dict, version: str = "v1") -> bool:
        await self._write_file(folder_path, version, "manifest.json", json.dumps(manifest, indent=2))
        return True

    async def delete_prompt(self, folder_path: str) -> bool:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pm_files WHERE folder_path = %s", (folder_path,))
        return True

    async def list_prompts(self) -> List[Dict]:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT folder_path FROM pm_files ORDER BY folder_path ASC"
            )
            return [{"folder_path": r["folder_path"]} for r in cursor.fetchall()]


def get_storage_service(user_id: str) -> StorageService:
    """Factory function to get the appropriate storage service based on user settings.

    Falls back to local storage if GitHub is not configured.
    """
    storage_mode = get_storage_mode(user_id)

    if storage_mode == "db":
        return DatabaseStorageService(user_id)
    if storage_mode == "local":
        return LocalStorageService(user_id)
    else:
        # Check if GitHub is actually configured
        settings = get_github_settings(user_id)
        if not settings or not settings.get("github_token"):
            # Fallback to local storage
            return LocalStorageService(user_id)
        return GitHubStorageService(user_id)
