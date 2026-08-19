from typing: Dict, List, Set
from enum import Enum
from dataclasses import dataclass


class Role(Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    DEVELOPER = "developer"
    VIEWER = "viewer"
    SERVICE = "service"


class Permission(Enum):
    READ_REVIEWS = "read_reviews"
    WRITE_REVIEWS = "write_reviews"
    MANAGE_HITL = "manage_hitl"
    VIEW_ECONOMICS = "view_economics"
    MANAGE_CONFIG = "manage_config"
    TRIGGER_INGESTION = "trigger_ingestion"


ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.ADMIN: {
        Permission.READ_REVIEWS,
        Permission.WRITE_REVIEWS,
        Permission.MANAGE_HITL,
        Permission.VIEW_ECONOMICS,
        Permission.MANAGE_CONFIG,
        Permission.TRIGGER_INGESTION,
    },
    Role.REVIEWER: {
        Permission.READ_REVIEWS,
        Permission.WRITE_REVIEWS,
        Permission.MANAGE_HITL,
        Permission.VIEW_ECONOMICS,
    },
    Role.DEVELOPER: {
        Permission.READ_REVIEWS,
        Permission.MANAGE_HITL,
    },
    Role.VIEWER: {
        Permission.READ_REVIEWS,
    },
    Role.SERVICE: {
        Permission.WRITE_REVIEWS,
        Permission.TRIGGER_INGESTION,
    },
}


@dataclass
class Principal:
    user_id: str
    roles: List[Role]
    
    def has_permission(self, permission: Permission) -> bool:
        for role in self.roles:
            if permission in ROLE_PERMISSIONS.get(role, set()):
                return True
        return False


def get_permissions_for_role(role: Role) -> Set[Permission]:
    return ROLE_PERMISSIONS.get(role, set())


def check_permission(principal: Principal, permission: Permission) -> bool:
    return principal.has_permission(permission)