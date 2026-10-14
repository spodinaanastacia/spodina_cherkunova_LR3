import strawberry
import httpx
import asyncio
import jwt
from typing import List, Optional
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

SECRET_KEY = "super-secret-key-for-lab"
ALGORITHM = "HS256"

app = FastAPI(title="GraphQL Gateway & Auth (Разработчик: Черкунова А.)")

# --- 1. REST AUTH-СЕРВИС ИЗ ЛР №2 ---
users_db = {} 

class AuthSchema(BaseModel):
    username: str = Field(..., description="Логин (email)")
    password: str = Field(..., description="Пароль")

"/api/auth/register", status_code=status.HTTP_201_CREATED
def register(user: AuthSchema):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="User already exists")
    users_db[user.username] = user.password 
    return {"message": "User registered successfully"}

"/api/auth/login"
def login(user: AuthSchema):
    if users_db.get(user.username) != user.password:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = jwt.encode({"sub": user.username}, SECRET_KEY, algorithm=ALGORITHM)
    return {"token": token}

# --- 2. GRAPHQL GATEWAY ---
REST_CATALOG_URL = "http://127.0.0"

ORDERS_DB = [
    {
        "id": "1001", 
        "userId": "123", 
        "createdAt": "2026-10-13 14:00:00", 
        "items": [{"productId": "1", "quantity": 1}, {"productId": "2", "quantity": 3}]
    },
    {
        "id": "1002", 
        "userId": "123", 
        "createdAt": "2026-10-13 15:30:00", 
        "items": [{"productId": "3", "quantity": 1}]
    }
]

async def batch_load_products(keys: List[str]) -> List["Product"]:
    async with httpx.AsyncClient() as client:
        tasks = [client.get(f"{REST_CATALOG_URL}/{product_id}") for product_id in keys]
        responses = await asyncio.gather(*tasks)
        
        loaded_products = []
        for response in responses:
            if response.status_code == 200:
                data = response.json()
                loaded_products.append(Product(id=str(data["id"]), name=data["name"], price=data["price"]))
            else:
                loaded_products.append(None)
        return loaded_products

product_loader = strawberry.dataloader.DataLoader(load_fn=batch_load_products)

@strawberry.type(description="Товар, запрашиваемый из Catalog Service по REST")
class Product:
    id: strawberry.ID = strawberry.field(description="Уникальный ID товара")
    name: str = strawberry.field(description="Наименование позиции")
    price: float = strawberry.field(description="Цена в рублях")

@strawberry.type(description="Элемент товарной позиции в заказе")
class OrderItem:
    quantity: int = strawberry.field(description="Количество единиц товара")
    
    description="Детали товара, подтягиваемые через DataLoader без N+1"
    async def product(self, root) -> Optional[Product]:
        return await product_loader.load(root["productId"])

@strawberry.type(description="Информация о самом заказе пользователя")
class Order:
    id: strawberry.ID = strawberry.field(description="Номер уникального заказа")
    userId: strawberry.ID = strawberry.field(description="ID покупателя")
    createdAt: str = strawberry.field(description="Дата совершения покупки")
    
    description="Список содержимого корзины"
    def items(self, root) -> List[OrderItem]:
        return [OrderItem(quantity=item["quantity"]) for item in root["items"]]

@strawberry.type
class Query:
    description="Запрос получения списка заказов пользователя по его личному ID"
    async def ordersByUserId(self, userId: strawberry.ID) -> List[Order]:
        user_orders = [order for order in ORDERS_DB if order["userId"] == userId]
        return [
            Order(id=order["id"], userId=order["userId"], createdAt=order["createdAt"]) 
            for order in user_orders
        ]

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema, introspection=True)
app.include_router(graphql_app, prefix="/graphql")