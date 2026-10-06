import datetime as dt
import json
import os
import secrets
from pathlib import Path

import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User, Role
import perms

# The signing secret is taken from SSG_APP_SECRET if set; otherwise a random
# one is generated once and kept in data/.secret so tokens survive restarts.
_DATA = Path(__file__).resolve().parent / "data"
_DATA.mkdir(parents=True, exist_ok=True)


def _load_secret() -> str:
    env = os.environ.get("SSG_APP_SECRET")
    if env:
        return env
    f = _DATA / ".secret"
    if f.exists():
        return f.read_text().strip()
    s = secrets.token_urlsafe(48)
    f.write_text(s)
    return s


SECRET_KEY = _load_secret()
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(username: str, role: str) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "role": role, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def _decode_user(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    try:
        username = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub")
    except JWTError:
        return None
    if not username:
        return None
    user = db.query(User).filter(User.username == username).first()
    return user if user and user.active else None


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user = _decode_user(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ------------------------------------------------------------ permissions ---

def is_admin(user: User) -> bool:
    return (user.role or "").strip().upper() == "ADMIN"


def user_permissions(db: Session, user: User) -> set[str]:
    if is_admin(user):
        return set(perms.ALL_KEYS)
    role = next((r for r in db.query(Role).all() if r.name.strip().lower() == (user.role or "").strip().lower()), None)
    if not role:
        return set()
    try:
        granted = set(json.loads(role.permissions or "[]"))
    except ValueError:
        return set()
    return {k for k in granted if k in perms.ALL_KEYS}


def seed_roles(db: Session) -> None:
    """Create the default roles if they don't exist yet (never overwrites edits)."""
    existing = {r.name.lower() for r in db.query(Role).all()}
    for name, keys in perms.DEFAULT_ROLES.items():
        if name.lower() not in existing:
            db.add(Role(name=name, permissions=json.dumps(keys)))
    db.commit()


# Permission keys introduced by the SSG AGT V1.84 sync. Existing databases keep the roles
# exactly as the admin edited them, so these new keys are added ONCE to the built-in roles
# (never to custom roles -- tick them in Admin -> Roles & Permissions) and never again.
_NEW_KEY_GRANTS = {
    "OPERATION": ["dashboard_generate", "monitoring_permanent_stop", "imports_google_sync", "imports_telegram_reports"],
    "User": ["dashboard_generate", "monitoring_permanent_stop", "imports_google_sync", "imports_telegram_reports"],
    "Viewer": ["monitoring_permanent_stop"],
}
_MIGRATION_ID = "ssg_v1_84_permission_keys"


def migrate_new_permissions(db: Session) -> None:
    marker = _DATA / ".perm_migrations.json"
    try:
        done = set(json.loads(marker.read_text())) if marker.exists() else set()
    except ValueError:
        done = set()
    if _MIGRATION_ID in done:
        return
    for role in db.query(Role).all():
        grants = next((v for k, v in _NEW_KEY_GRANTS.items() if k.lower() == role.name.strip().lower()), None)
        if not grants:
            continue
        try:
            current = json.loads(role.permissions or "[]")
        except ValueError:
            current = []
        merged = list(dict.fromkeys(list(current) + grants))
        if merged != current:
            role.permissions = json.dumps(merged)
    db.commit()
    done.add(_MIGRATION_ID)
    marker.write_text(json.dumps(sorted(done)))


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def perm(view: str | tuple[str, ...], action: str | None = None):
    """Dependency factory: ``Depends(perm('master_list', 'master_edit'))``.

    ``view`` may be a tuple (any-of). If ``action`` is given the user needs a
    matching view key AND the action key — an action never grants access alone.
    """
    views = (view,) if isinstance(view, str) else tuple(view)

    def dep(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        granted = user_permissions(db, user)
        if not any(v in granted for v in views) or (action and action not in granted):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to do this")
        return user

    return dep
