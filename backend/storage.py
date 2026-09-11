import asyncio, io, logging, os, uuid
from datetime import datetime, timezone
import requests
from PIL import Image, ImageOps
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

logger = logging.getLogger("navyug.storage")
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "navyug"
storage_key = None


def init_storage(force=False):
    global storage_key
    if storage_key and not force: return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path, data, content_type):
    resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(), "Content-Type": content_type}, data=data, timeout=120)
    if resp.status_code == 404:
        resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(force=True), "Content-Type": content_type}, data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def get_object(path):
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage()}, timeout=60)
    if resp.status_code == 404:
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(force=True)}, timeout=60)
    resp.raise_for_status()
    return resp.content


def compress(data):
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    im.thumbnail((1200, 1200), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=82, optimize=True)
    return buf.getvalue()


class HideIn(BaseModel): url: str


def register(ctx):
    db, admin_user = ctx["db"], ctx["admin_user"]
    router = APIRouter(prefix="/api/photos")
    public = lambda d: {"id": d["id"], "name": d["name"], "url": f"/api/photos/file/{d['id']}"}

    @router.get("")
    async def list_photos(_: dict = Depends(admin_user)):
        uploads = await db.photos.find({"is_deleted": False}).sort("created_at", -1).to_list(500)
        hidden = await db.settings.find_one({"key": "hidden_photos"}) or {}
        return {"uploads": [public(x) for x in uploads], "hidden": hidden.get("urls", [])}

    @router.post("")
    async def upload_photo(file: UploadFile = File(...), _: dict = Depends(admin_user)):
        if not (file.content_type or "").startswith("image/"): raise HTTPException(400, "Please upload an image")
        raw = await file.read()
        if len(raw) > 15 * 1024 * 1024: raise HTTPException(400, "Image is too large (max 15 MB)")
        try: data = await asyncio.to_thread(compress, raw)
        except Exception: raise HTTPException(400, "Could not read that image")
        photo_id = uuid.uuid4().hex[:12]
        try: result = await asyncio.to_thread(put_object, f"{APP_NAME}/dishes/{photo_id}.jpg", data, "image/jpeg")
        except Exception as e:
            logger.error(f"Upload failed: {e}"); raise HTTPException(424, "Photo storage is unavailable right now")
        doc = {"id": photo_id, "name": os.path.splitext(file.filename or "photo")[0][:60], "storage_path": result["path"], "content_type": "image/jpeg", "size": result.get("size", len(data)), "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat()}
        await db.photos.insert_one(doc)
        return public(doc)

    @router.get("/file/{photo_id}")
    async def photo_file(photo_id: str):
        doc = await db.photos.find_one({"id": photo_id, "is_deleted": False})
        if not doc: raise HTTPException(404, "Photo not found")
        data = await asyncio.to_thread(get_object, doc["storage_path"])
        return Response(content=data, media_type=doc["content_type"], headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @router.delete("/{photo_id}")
    async def delete_photo(photo_id: str, _: dict = Depends(admin_user)):
        r = await db.photos.update_one({"id": photo_id}, {"$set": {"is_deleted": True}})
        if not r.matched_count: raise HTTPException(404, "Photo not found")
        return {"ok": True}

    @router.post("/hide")
    async def hide_photo(data: HideIn, _: dict = Depends(admin_user)):
        await db.settings.update_one({"key": "hidden_photos"}, {"$addToSet": {"urls": data.url}}, upsert=True)
        return {"ok": True}

    return router
