from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import logging, os, secrets, uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
import bcrypt, jwt
from bson import ObjectId
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, field_validator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("navyug")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="Navyug Catering API")
api = APIRouter(prefix="/api")
JWT_SECRET = os.environ["JWT_SECRET"]
SETUP_KEY = os.environ["ADMIN_SETUP_KEY"]

def now(): return datetime.now(timezone.utc).isoformat()
def oid(value): return str(value) if isinstance(value, ObjectId) else value
def public(doc):
    if not doc: return None
    doc = {k: oid(v) for k, v in doc.items() if k not in {"_id", "password_hash"}}
    return doc
def hash_password(password): return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def verify_password(password, hashed): return bcrypt.checkpw(password.encode(), hashed.encode())
def token(user):
    return jwt.encode({"sub": str(user["_id"]), "exp": datetime.now(timezone.utc)+timedelta(days=7)}, JWT_SECRET, algorithm="HS256")

async def current_user(request: Request):
    value = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not value: raise HTTPException(401, "Please log in to continue")
    try: payload = jwt.decode(value, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError: raise HTTPException(401, "Your session has expired")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user: raise HTTPException(401, "User not found")
    return user
async def admin_user(user=Depends(current_user)):
    if user.get("role") != "admin": raise HTTPException(403, "Admin access required")
    return user

class Register(BaseModel): name: str; email: EmailStr; phone: str = ""; password: str = Field(min_length=6); address: str = ""
class Login(BaseModel): email: str; password: str
class MenuIn(BaseModel): name: str; description: str; category: str; price: float = Field(gt=0); image: str; is_vegetarian: bool = True; available: bool = True
class OrderIn(BaseModel): customer_name: str; phone: str; email: Optional[EmailStr] = None; address: str; special_instructions: str = ""; items: list[dict]
class CateringIn(BaseModel):
    name: str; phone: str; email: Optional[EmailStr] = None; event_type: str; event_date: str; guests: int = Field(gt=0); location: str; requirements: str = ""; message: str = ""
    @field_validator("email", mode="before")
    @classmethod
    def blank_email(cls, value): return None if value == "" else value
class ContactIn(BaseModel): name: str; contact: str; message: str
class StatusIn(BaseModel): status: str
class SetupIn(BaseModel): name: str; email: str; password: str = Field(min_length=6); setup_key: str

@api.get("/")
async def root(): return {"message": "Navyug Catering API"}

@api.post("/auth/register")
async def register(data: Register, response: Response):
    email = data.email.lower()
    if await db.users.find_one({"email": email}): raise HTTPException(409, "An account with this email already exists")
    doc = {"name": data.name, "email": email, "phone": data.phone, "address": data.address, "password_hash": hash_password(data.password), "role": "customer", "created_at": now()}
    result = await db.users.insert_one(doc); doc["_id"] = result.inserted_id
    response.set_cookie("access_token", token(doc), httponly=True, samesite="lax", max_age=604800)
    return public(doc)
@api.post("/auth/login")
async def login(data: Login, response: Response):
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not verify_password(data.password, user["password_hash"]): raise HTTPException(401, "Email or password is incorrect")
    response.set_cookie("access_token", token(user), httponly=True, samesite="lax", max_age=604800)
    return public(user)
@api.post("/auth/logout")
async def logout(response: Response): response.delete_cookie("access_token"); return {"ok": True}
@api.get("/auth/me")
async def me(user=Depends(current_user)): return public(user)
@api.post("/admin/setup")
async def setup_admin(data: SetupIn, response: Response):
    if data.setup_key != SETUP_KEY: raise HTTPException(403, "Invalid setup key")
    if await db.users.find_one({"role": "admin"}): raise HTTPException(409, "An admin is already configured")
    doc = {"name": data.name, "email": data.email.lower(), "password_hash": hash_password(data.password), "phone": "", "address": "", "role": "admin", "created_at": now()}
    result = await db.users.insert_one(doc); doc["_id"] = result.inserted_id
    response.set_cookie("access_token", token(doc), httponly=True, samesite="lax", max_age=604800)
    return public(doc)
@api.get("/admin/setup-status")
async def setup_status(): return {"configured": bool(await db.users.find_one({"role": "admin"}))}

@api.get("/menu")
async def menu(): return [public(x) for x in await db.menu.find({}).sort("category", 1).to_list(100)]
@api.post("/menu")
async def create_menu(data: MenuIn, _: dict = Depends(admin_user)):
    doc = data.model_dump(); doc.update({"id": uuid.uuid4().hex[:10], "created_at": now()}); await db.menu.insert_one(doc); return public(doc)
@api.put("/menu/{item_id}")
async def update_menu(item_id: str, data: MenuIn, _: dict = Depends(admin_user)):
    result = await db.menu.update_one({"id": item_id}, {"$set": data.model_dump()})
    if not result.matched_count: raise HTTPException(404, "Menu item not found")
    return public(await db.menu.find_one({"id": item_id}))
@api.delete("/menu/{item_id}")
async def delete_menu(item_id: str, _: dict = Depends(admin_user)):
    await db.menu.delete_one({"id": item_id}); return {"ok": True}

@api.post("/orders")
async def create_order(data: OrderIn, user=Depends(current_user)):
    subtotal = 0; items = []
    for requested in data.items:
        item = await db.menu.find_one({"id": requested.get("menu_id"), "available": True})
        quantity = int(requested.get("quantity", 0))
        if not item or quantity < 1: raise HTTPException(400, "One of your selected dishes is unavailable")
        subtotal += item["price"] * quantity
        items.append({"menu_id": item["id"], "name": item["name"], "price": item["price"], "quantity": quantity})
    delivery = 40 if subtotal < 500 else 0
    doc = {"order_id": "NV-" + secrets.token_hex(4).upper(), "user_id": str(user["_id"]), "customer_name": data.customer_name, "phone": data.phone, "email": data.email, "address": data.address, "special_instructions": data.special_instructions, "items": items, "subtotal": subtotal, "delivery_fee": delivery, "total": subtotal+delivery, "payment_status": "Pending", "status": "Pending", "created_at": now()}
    await db.orders.insert_one(doc); return public(doc)
@api.get("/orders")
async def my_orders(user=Depends(current_user)): return [public(x) for x in await db.orders.find({"user_id": str(user["_id"])}).sort("created_at", -1).to_list(100)]
@api.get("/orders/all")
async def all_orders(_: dict = Depends(admin_user)): return [public(x) for x in await db.orders.find({}).sort("created_at", -1).to_list(200)]
@api.patch("/orders/{order_id}")
async def order_status(order_id: str, data: StatusIn, _: dict = Depends(admin_user)):
    await db.orders.update_one({"order_id": order_id}, {"$set": {"status": data.status}}); return {"ok": True}

@api.post("/catering")
async def catering(data: CateringIn):
    doc = data.model_dump(); doc.update({"inquiry_id": "CAT-"+secrets.token_hex(3).upper(), "status": "New", "created_at": now()}); await db.catering.insert_one(doc); return public(doc)
@api.get("/catering")
async def catering_list(_: dict = Depends(admin_user)): return [public(x) for x in await db.catering.find({}).sort("created_at", -1).to_list(200)]
@api.patch("/catering/{inquiry_id}")
async def catering_status(inquiry_id: str, data: StatusIn, _: dict = Depends(admin_user)): await db.catering.update_one({"inquiry_id": inquiry_id}, {"$set": {"status": data.status}}); return {"ok": True}
@api.post("/contact")
async def contact(data: ContactIn):
    doc = data.model_dump(); doc.update({"inquiry_id": "MSG-"+secrets.token_hex(3).upper(), "status": "New", "created_at": now()}); await db.contacts.insert_one(doc); return public(doc)
@api.get("/contact")
async def contact_list(_: dict = Depends(admin_user)): return [public(x) for x in await db.contacts.find({}).sort("created_at", -1).to_list(200)]
@api.patch("/contact/{inquiry_id}")
async def contact_status(inquiry_id: str, data: StatusIn, _: dict = Depends(admin_user)):
    await db.contacts.update_one({"inquiry_id": inquiry_id}, {"$set": {"status": data.status}})
    return {"ok": True}

async def seed_menu():
    if await db.menu.count_documents({}): return
    images = ["https://images.unsplash.com/photo-1627366422957-3efa9c6df0fc?auto=format&fit=crop&w=900&q=80", "https://images.unsplash.com/photo-1585937421612-70a008356fbe?auto=format&fit=crop&w=900&q=80", "https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=900&q=80"]
    dishes = [("Dal Tadka","Yellow lentils tempered with garlic, cumin and ghee.","Dal",180),("Dal Makhani","Slow-cooked black lentils, rich and creamy.","Dal",220),("Punjabi Chole","Robust chickpeas simmered with Punjabi spices.","Punjabi",200),("Plain Rice","Steamed long-grain rice, light and fluffy.","Rice",120),("Jeera Rice","Basmati rice tossed with roasted cumin.","Rice",140),("Matar Pulao","Fragrant rice with sweet green peas.","Rice",160),("Vegetable Tawa Pulao","Mumbai-style spiced rice with fresh vegetables.","Rice",190),("Kadhai Paneer","Paneer, peppers and onion in a bright kadai masala.","Paneer",260),("Matar Paneer","Soft paneer and peas in a homestyle gravy.","Paneer",240)]
    await db.menu.insert_many([{ "id": uuid.uuid4().hex[:10], "name": n, "description": d, "category": c, "price": p, "image": images[i%3], "is_vegetarian": True, "available": True, "created_at": now()} for i,(n,d,c,p) in enumerate(dishes)])
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True); await seed_menu()
@app.on_event("shutdown")
async def shutdown(): client.close()
app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000"), "https://navyug-taste-love.preview.emergentagent.com"], allow_methods=["*"], allow_headers=["*"])