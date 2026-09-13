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
import asyncio
import payments as payments_module
import emailer
import storage as storage_module
import whatsapp

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
class MenuIn(BaseModel): name: str; description: str; category: str; section: str = "tiffin"; price: float = Field(gt=0); image: str; is_vegetarian: bool = True; available: bool = True; is_special: bool = False
class OrderIn(BaseModel): customer_name: str; phone: str; email: Optional[EmailStr] = None; address: str; special_instructions: str = ""; items: list[dict]; event_datetime: Optional[str] = None; utr: Optional[str] = None; payment_method: str = "COD"
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
    email = data.email.strip().lower()
    if await db.users.find_one({"email": email}): raise HTTPException(409, "An account with this email already exists")
    doc = {"name": data.name, "email": email, "phone": data.phone, "address": data.address, "password_hash": hash_password(data.password), "role": "customer", "created_at": now()}
    result = await db.users.insert_one(doc); doc["_id"] = result.inserted_id
    response.set_cookie("access_token", token(doc), httponly=True, samesite="lax", max_age=604800)
    return public(doc)
@api.post("/auth/login")
async def login(data: Login, response: Response):
    user = await db.users.find_one({"email": data.email.strip().lower()})
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
async def menu(): return [public(x) for x in await db.menu.find({}).sort("created_at", 1).to_list(200)]
@api.get("/payments/upi/config")
async def upi_config():
    upi_id = os.environ.get("UPI_ID", "").strip()
    return {"enabled": bool(upi_id), "upi_id": upi_id, "payee_name": os.environ.get("UPI_PAYEE_NAME", "Navyug Catering & Tiffin"), "whatsapp_number": os.environ.get("ORDER_WHATSAPP_NUMBER", "")}
@api.get("/menu/specials")
async def specials(): return [public(x) for x in await db.menu.find({"is_special": True, "available": True}).sort("created_at", 1).to_list(10)]
@api.get("/menu/most-ordered")
async def most_ordered():
    pipeline = [{"$unwind": "$items"}, {"$group": {"_id": "$items.menu_id", "ordered": {"$sum": "$items.quantity"}}}, {"$sort": {"ordered": -1}}, {"$limit": 4}]
    ranked = await db.orders.aggregate(pipeline).to_list(4)
    ids = [x["_id"] for x in ranked]
    dishes = {x["id"]: public(x) for x in await db.menu.find({"id": {"$in": ids}, "available": True}).to_list(20)}
    result = [{**dishes[x["_id"]], "ordered": x["ordered"]} for x in ranked if x["_id"] in dishes]
    if result: return result
    featured = ["Paneer Butter Masala", "Dal Tadka", "Vegetable Poha", "Aloo Besan Tikki"]
    dishes = {x["name"]: public(x) for x in await db.menu.find({"name": {"$in": featured}, "available": True}).to_list(10)}
    return [{**dishes[name], "ordered": 0} for name in featured if name in dishes]
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
    doc = {"order_id": "NV-" + secrets.token_hex(4).upper(), "user_id": str(user["_id"]), "customer_name": data.customer_name, "phone": data.phone, "email": data.email, "address": data.address, "special_instructions": data.special_instructions, "event_datetime": data.event_datetime, "utr": (data.utr or "").strip() or None, "payment_method": data.payment_method, "items": items, "subtotal": subtotal, "delivery_fee": delivery, "total": subtotal+delivery, "payment_status": "Pending", "status": "Pending", "created_at": now()}
    await db.orders.insert_one(doc)
    asyncio.create_task(whatsapp.notify_new_order(doc))
    if doc.get("email"):
        asyncio.create_task(emailer.send_order_confirmation(doc))
    return public(doc)
@api.get("/orders")
async def my_orders(user=Depends(current_user)): return [public(x) for x in await db.orders.find({"user_id": str(user["_id"])}).sort("created_at", -1).to_list(100)]
@api.get("/orders/all")
async def all_orders(_: dict = Depends(admin_user)): return [public(x) for x in await db.orders.find({}).sort("created_at", -1).to_list(200)]
@api.patch("/orders/{order_id}")
async def order_status(order_id: str, data: StatusIn, _: dict = Depends(admin_user)):
    await db.orders.update_one({"order_id": order_id}, {"$set": {"status": data.status}})
    order = await db.orders.find_one({"order_id": order_id})
    if order:
        asyncio.create_task(whatsapp.notify_customer_status(order, data.status))
        if order.get("email"): asyncio.create_task(emailer.send_order_status(order, data.status))
    return {"ok": True}

@api.post("/catering")
async def catering(data: CateringIn):
    doc = data.model_dump(); doc.update({"inquiry_id": "CAT-"+secrets.token_hex(3).upper(), "status": "New", "created_at": now()})
    await db.catering.insert_one(doc)
    asyncio.create_task(whatsapp.notify_catering(doc))
    if doc.get("email"):
        asyncio.create_task(emailer.send_catering_ack(doc))
    return public(doc)
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
    images = ["https://images.unsplash.com/photo-1627366422957-3efa9c6df0fc?auto=format&fit=crop&w=900&q=80", "https://images.unsplash.com/photo-1585937421612-70a008356fbe?auto=format&fit=crop&w=900&q=80", "https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=900&q=80"]
    S, T = "snacks", "tiffin"
    dishes = [
        ("Stir Fried Mini Idlis","Bite-sized idlis tossed in a light tempering.","Snacks",80,S,"mini-idlis"),("Stir Fried Mini Vegetable Idli","Mini idlis stir-fried with crunchy vegetables.","Snacks",80,S,None),("Vegetable Mayo Sandwich","Fresh vegetables and creamy mayo between soft bread.","Snacks",80,S,"veg-sandwich"),("Aloo Besan Tikki","Crisp potato and gram-flour patties.","Snacks",80,S,"aloo-besan-tikki"),("Sabudana Tikki","Golden sago patties, crunchy outside and soft inside.","Snacks",80,S,"sabudana-tikki"),("Crispy Corn","Sweet corn fried crisp and tossed in spices.","Snacks",80,S,None),("Pav Bhaji","Buttery mashed vegetable bhaji with toasted pav.","Snacks",80,S,None),("Idli Sambhar","Steamed idlis with warm sambhar and chutney.","Snacks",80,S,None),("Vegetable Sewai","Savoury vermicelli tempered with vegetables.","Snacks",80,S,None),("Pasta / Macaroni","Home-style pasta in a comforting sauce.","Snacks",80,S,None),("French Fries","Crisp golden fries, lightly salted.","Snacks",80,S,"french-fries"),("Samosa","Flaky pastry filled with spiced potatoes and peas.","Snacks",80,S,None),("Cutlets","Crisp vegetable cutlets served with chutney.","Snacks",80,S,"cutlets"),("Plain Idli","Soft steamed idli, priced per piece.","Snacks",10,S,None),
        ("Vegetable Poha","Light flattened rice with vegetables, garnished with pomegranate.","Breakfast",80,T,"veg-poha"),("Vegetable Sewai (Breakfast)","Savoury vermicelli tempered with vegetables.","Breakfast",80,T,None),("Aloo Sabji + Poori","Spiced potato curry with puffed pooris.","Breakfast",80,T,None),("Mini Fried Idlis + Green Chutney","Crisp mini idlis with fresh green chutney.","Breakfast",80,T,"mini-idlis"),("Besan Batata Tikki","Gram-flour and potato tikkis, pan-crisped.","Breakfast",80,T,"aloo-besan-tikki"),("Vegetable Mayo Sandwich (Breakfast)","Fresh vegetables and creamy mayo between soft bread.","Breakfast",80,T,"sandwich-plate"),("Idli Sambhar (Breakfast)","Steamed idlis with warm sambhar.","Breakfast",80,T,None),("Mangodi","Moong dal nuggets in a homestyle preparation.","Breakfast",80,T,None),("Aloo Paratha","Stuffed potato paratha, served with curd.","Breakfast",80,T,None),("Mooli Paratha","Radish-stuffed paratha, crisp on the tawa.","Breakfast",80,T,None),
        ("Dal Makhani","Slow-cooked black lentils, rich and creamy.","Dal",120,T,None),("Punjabi Rajma","Kidney beans in a comforting Punjabi gravy.","Dal",120,T,"rajma"),("Punjabi Chole","Chickpeas simmered with Punjabi spices.","Dal",120,T,None),("Mix Dal","Five lentils cooked together, home style.","Dal",120,T,None),("Dal Tadka","Yellow lentils tempered with garlic and cumin.","Dal",120,T,"dal-tadka"),("Langar Dal","Gurudwara-style slow-cooked dal.","Dal",120,T,None),("Yellow Moong","Light yellow moong dal, gently spiced.","Dal",120,T,None),
        ("Matar Mushroom","Mushrooms and peas in a homestyle gravy.","Gravy",120,T,None),("Kadhai Mushroom","Mushrooms in a bright kadhai masala.","Gravy",120,T,None),("Matar Paneer","Soft paneer and peas in tomato gravy.","Gravy",120,T,None),("Shahi Paneer","Paneer in a rich, royal cashew gravy.","Gravy",120,T,None),("Kadhai Paneer","Paneer, peppers and onion in kadhai masala.","Gravy",120,T,None),("Paneer Butter Masala","Paneer in a buttery tomato gravy.","Gravy",120,T,"paneer-butter-masala"),("Palak Paneer","Paneer in smooth spinach gravy.","Gravy",120,T,None),("Palak Corn","Sweet corn in creamy spinach.","Gravy",120,T,None),("Kadhi Pakoda","Yogurt kadhi with soft pakodas.","Gravy",120,T,"kadhi-pakoda"),("Aloo Matar","Potatoes and peas in a light gravy.","Gravy",120,T,None),("Aloo Kofta","Potato koftas in a silky gravy.","Gravy",120,T,None),
        ("Chapati","Soft whole-wheat chapati, per piece.","Roti & Rice",20,T,None),("Plain Rice (1 bowl)","Steamed rice, one bowl.","Roti & Rice",50,T,"plain-rice"),("Jeera Rice (1 bowl)","Cumin-tossed rice, one bowl.","Roti & Rice",50,T,"jeera-rice"),
        ("Gulab Jamun","Soft milk dumplings in rose syrup.","Desi Meetha",80,T,None),("Kheer","Slow-cooked rice pudding with cardamom.","Desi Meetha",80,T,None),("Suji Halwa","Warm semolina halwa with ghee and nuts.","Desi Meetha",80,T,None),
        ("Chai","Hot masala chai.","Drinks",20,T,None),("Cold Drink","Chilled soft drink.","Drinks",40,T,None),
        ("Mix Veg","Seasonal vegetables in a homestyle gravy, topped with cheese.","Gravy",120,T,"mix-veg"),("Aloo Sabzi","Dry potato sabzi, tempered and finished with a little cheese.","Dry Sabzi",80,T,"aloo-sabzi"),("Green Salad","Fresh carrot, cucumber and radish salad.","Salad & Raita",50,T,"green-salad"),("Onion Salad","Crisp onion rings with tomato and cucumber.","Salad & Raita",50,T,"onion-salad"),("Raita","Chilled curd raita with a gentle tempering.","Salad & Raita",50,T,"raita"),("Veg Pulao (1 bowl)","Fragrant rice with seasonal vegetables.","Roti & Rice",50,T,"veg-pulao"),("Veg Noodles","Street-style vegetable noodles.","Snacks",80,S,"veg-noodles"),
    ]
    if await db.menu.count_documents({}) > 0: return
    await db.menu.insert_many([{"id": uuid.uuid4().hex[:10], "name": n, "description": d, "category": c, "section": sec, "price": p, "image": f"/photos/{img}.jpg" if img else images[i%3], "is_vegetarian": True, "available": True, "created_at": now()} for i,(n,d,c,p,sec,img) in enumerate(dishes)])
    await db.settings.update_one({"key": "menu_seed"}, {"$set": {"version": 3}}, upsert=True)
async def seed_admin():
    email, password = os.environ.get("ADMIN_EMAIL", "").strip().lower(), os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password: return
    existing = await db.users.find_one({"email": email})
    if existing is None:
        await db.users.insert_one({"name": "Navyug Owner", "email": email, "phone": "", "address": "", "password_hash": hash_password(password), "role": "admin", "created_at": now()})
        logger.info("Admin account seeded")
    elif existing.get("role") != "admin" or not verify_password(password, existing["password_hash"]):
        await db.users.update_one({"email": email}, {"$set": {"role": "admin", "password_hash": hash_password(password)}})
        logger.info("Admin account updated")

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.razorpay_webhook_events.create_index("event_id", unique=True)
    await seed_menu()
    await seed_admin()
    try: await asyncio.to_thread(storage_module.init_storage); logger.info("Storage initialized")
    except Exception as e: logger.error(f"Storage init failed: {e}")
@app.on_event("shutdown")
async def shutdown(): client.close()
app.include_router(api)
app.include_router(payments_module.register({"db": db, "current_user": current_user}))
app.include_router(storage_module.register({"db": db, "admin_user": admin_user}))
app.include_router(whatsapp.register({"admin_user": admin_user}))
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"] if os.environ.get("CORS_ORIGINS", "*").strip() == "*" else [o.strip() for o in os.environ["CORS_ORIGINS"].split(",") if o.strip()], allow_methods=["*"], allow_headers=["*"])