"""SSG AGT Pro — a single FastAPI app: unified auth/users/roles, the SSG AGT
account-monitoring engine (backend/ssg/logic_core.py, unchanged) exposed as a
JSON API (ssg_api.py), and the built React frontend served as static files.
"""
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import (
    hash_password, verify_password, create_token, get_current_user, perm,
    seed_roles, migrate_new_permissions, user_permissions, is_admin,
)
from database import Base, engine, get_db
from models import User, Role
import perms as perms_catalog
import ssg_api

Base.metadata.create_all(bind=engine)


def _ensure_user_columns() -> None:
    """create_all() never alters an existing table, so add the per-user Last Generate column
    to databases created before it existed."""
    from sqlalchemy import inspect, text
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    if "last_generate_at" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_generate_at VARCHAR"))


_ensure_user_columns()

app = FastAPI(title="SSG AGT Pro")
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.on_event("startup")
def seed_admin():
    db = next(get_db())
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin123"), role="ADMIN"))
        db.commit()
    seed_roles(db)
    migrate_new_permissions(db)
    db.close()
    # Telegram bot listener (only does anything once a bot token is configured)
    try:
        ssg_api.INTEGRATIONS.start_telegram_listener()
    except Exception:
        pass


# ------------------------------------------------------------------- AUTH ---

def _session_payload(user: User, db: Session):
    return {"role": user.role, "username": user.username,
            "permissions": sorted(user_permissions(db, user)), "is_admin": is_admin(user),
            "last_generate_at": user.last_generate_at or ""}


@app.post("/api/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token = create_token(user.username, user.role)
    return {"access_token": token, "token_type": "bearer", **_session_payload(user, db)}


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _session_payload(user, db)


# ------------------------------------------------------------ USERS / ROLES ---

def _role_names(db: Session) -> set[str]:
    return {r.name.lower() for r in db.query(Role).all()} | {"admin"}


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "Viewer"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


@app.get("/api/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(perm("admin_users"))):
    rows = sorted(db.query(User).all(), key=lambda u: (u.username.lower() != "admin", u.username.lower()))
    return [{"id": u.id, "username": u.username, "role": u.role, "active": u.active} for u in rows]


@app.post("/api/users")
def create_user(payload: UserCreate, db: Session = Depends(get_db), user: User = Depends(perm("admin_users", "admin_users_edit"))):
    name = payload.username.strip()
    if not name or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    if db.query(User).filter(User.username == name).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if payload.role.lower() not in _role_names(db):
        raise HTTPException(status_code=400, detail="Unknown role")
    u = User(username=name, password_hash=hash_password(payload.password), role=payload.role)
    db.add(u)
    db.commit()
    return {"ok": True, "id": u.id}


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), user: User = Depends(perm("admin_users", "admin_users_edit"))):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.username is not None and payload.username.strip() != target.username:
        if db.query(User).filter(User.username == payload.username.strip()).first():
            raise HTTPException(status_code=400, detail="Username already exists")
        target.username = payload.username.strip()
    if payload.role is not None:
        if payload.role.lower() not in _role_names(db):
            raise HTTPException(status_code=400, detail="Unknown role")
        if is_admin(target) and payload.role.upper() != "ADMIN" and \
                db.query(User).filter(User.role.ilike("admin"), User.active.is_(True)).count() <= 1:
            raise HTTPException(status_code=400, detail="You can't demote the last active admin")
        target.role = payload.role
    if payload.active is not None:
        if payload.active is False and target.id == user.id:
            raise HTTPException(status_code=400, detail="You can't disable your own account")
        target.active = payload.active
    if payload.password:
        target.password_hash = hash_password(payload.password)
    db.commit()
    return {"ok": True}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(perm("admin_users", "admin_users_delete"))):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account")
    db.delete(target)
    db.commit()
    return {"ok": True}


class RoleIn(BaseModel):
    name: Optional[str] = None
    permissions: Optional[list[str]] = None


@app.get("/api/roles")
def list_roles(db: Session = Depends(get_db), user: User = Depends(perm(("admin_roles", "admin_users")))):
    import json as _json
    roles = []
    for r in db.query(Role).order_by(Role.name).all():
        try:
            keys = [k for k in _json.loads(r.permissions or "[]") if k in perms_catalog.ALL_KEYS]
        except ValueError:
            keys = []
        locked = r.name.lower() == "admin"
        users_count = db.query(User).filter(User.role.ilike(r.name)).count()
        roles.append({"id": r.id, "name": r.name, "permissions": perms_catalog.ALL_KEYS if locked else keys,
                      "locked": locked, "users": users_count})
    tree = [{"key": g, "label": lbl, "items": [{"key": k, "label": l} for k, l in items]}
            for g, lbl, items in perms_catalog.PERMISSION_TREE]
    return {"roles": roles, "catalog": tree}


@app.post("/api/roles")
def create_role(payload: RoleIn, db: Session = Depends(get_db), user: User = Depends(perm("admin_roles", "admin_roles_edit"))):
    import json as _json
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")
    if name.lower() in _role_names(db):
        raise HTTPException(status_code=400, detail="A role with that name already exists")
    keys = [k for k in (payload.permissions or []) if k in perms_catalog.ALL_KEYS]
    db.add(Role(name=name, permissions=_json.dumps(keys)))
    db.commit()
    return {"ok": True}


@app.patch("/api/roles/{role_id}")
def update_role(role_id: int, payload: RoleIn, db: Session = Depends(get_db), user: User = Depends(perm("admin_roles", "admin_roles_edit"))):
    import json as _json
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.name.lower() == "admin":
        raise HTTPException(status_code=400, detail="The Admin role always has full access and can't be edited")
    if payload.name and payload.name.strip() != role.name:
        new = payload.name.strip()
        if new.lower() in _role_names(db):
            raise HTTPException(status_code=400, detail="A role with that name already exists")
        db.query(User).filter(User.role.ilike(role.name)).update({User.role: new}, synchronize_session=False)
        role.name = new
    if payload.permissions is not None:
        role.permissions = _json.dumps([k for k in payload.permissions if k in perms_catalog.ALL_KEYS])
    db.commit()
    return {"ok": True}


@app.delete("/api/roles/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db), user: User = Depends(perm("admin_roles", "admin_roles_delete"))):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.name.lower() == "admin":
        raise HTTPException(status_code=400, detail="The Admin role can't be deleted")
    if db.query(User).filter(User.role.ilike(role.name)).count():
        raise HTTPException(status_code=400, detail="Reassign the users of this role first")
    db.delete(role)
    db.commit()
    return {"ok": True}


app.include_router(ssg_api.router)


# -------------------------------------------------------- STATIC FRONTEND ---

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
