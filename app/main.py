from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.database.connection import get_db_connection, init_db
from mysql.connector import Error
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import timedelta

class UserBase(BaseModel):
    name: str
    email: str
    location: Optional[str] = None

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class DeviceBase(BaseModel):
    device_id: str

class Device(DeviceBase):
    id: int
    user_id: int
    registered_at: datetime

    class Config:
        from_attributes = True


class SensorData(BaseModel):
    id: int
    device_id: int
    timestamp: datetime
    temperature: Optional[float] = None
    humidity: Optional[float] = None

    class Config:
        from_attributes = True


class WardrobeItemBase(BaseModel):
    item_name: str
    category: Optional[str] = None

class WardrobeItem(WardrobeItemBase):
    id: int
    user_id: int
    added_at: datetime

    class Config:
        from_attributes = True


@asynccontextmanager
def init_db():
    conn = get_db_connection()
    if not conn:
        raise Exception("Database connection failed")
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            location VARCHAR(255),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            device_id VARCHAR(255) NOT NULL UNIQUE,
            registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            device_id INT NOT NULL,
            timestamp DATETIME NOT NULL,
            temperature FLOAT,
            humidity FLOAT,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS wardrobe (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            item_name VARCHAR(255) NOT NULL,
            category VARCHAR(255),
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)
        conn.commit()
    except Error as e:
        conn.rollback()
        raise Exception(f"Database initialization failed: {str(e)}")
    finally:
        cursor.close()
        conn.close()

app = FastAPI()

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Task Management API. Visit /docs for the API documentation."}


SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(email: str, password: str):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return user
    finally:
        cursor.close()
        conn.close()

def create_access_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        db = SessionLocal()
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/signup", response_model=User)
async def signup(user: UserCreate):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (user.email,))
        existing_user = cursor.fetchone()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_password = get_password_hash(user.password)
        cursor.execute("""
        INSERT INTO users (name, email, password_hash, location)
        VALUES (%s, %s, %s, %s)
        """, (user.name, user.email, hashed_password, user.location))
        conn.commit()
        
        cursor.execute("SELECT * FROM users WHERE email = %s", (user.email,))
        new_user = cursor.fetchone()
        return new_user
    finally:
        cursor.close()
        conn.close()

@app.post("/login")
async def login(email: str, password: str):
    user = authenticate_user(email, password)
    access_token = create_access_token(
        data={"sub": user["email"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/wardrobe/", response_model=WardrobeItem)
async def add_wardrobe_item(item: WardrobeItemBase, token: str = Depends(oauth2_scheme)):
    user = get_current_user(token)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
        INSERT INTO wardrobe (user_id, item_name, category)
        VALUES (%s, %s, %s)
        """, (user["id"], item.item_name, item.category))
        conn.commit()
        
        cursor.execute("SELECT * FROM wardrobe WHERE id = LAST_INSERT_ID()")
        new_item = cursor.fetchone()
        return new_item
    finally:
        cursor.close()
        conn.close()

@app.get("/wardrobe/", response_model=List[WardrobeItem])
async def get_wardrobe_items(token: str = Depends(oauth2_scheme)):
    user = get_current_user(token)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM wardrobe WHERE user_id = %s", (user["id"],))
        items = cursor.fetchall()
        return items
    finally:
        cursor.close()
        conn.close()

@app.post("/devices/", response_model=Device)
async def register_device(device: DeviceBase, token: str = Depends(oauth2_scheme)):
    user = get_current_user(token)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
        INSERT INTO devices (user_id, device_id)
        VALUES (%s, %s)
        """, (user["id"], device.device_id))
        conn.commit()
        
        cursor.execute("SELECT * FROM devices WHERE id = LAST_INSERT_ID()")
        new_device = cursor.fetchone()
        return new_device
    finally:
        cursor.close()
        conn.close()

@app.post("/sensor-data/")
async def add_sensor_data(device_id: int, temperature: float, humidity: float):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO sensor_data (device_id, timestamp, temperature, humidity)
        VALUES (%s, NOW(), %s, %s)
        """, (device_id, temperature, humidity))
        conn.commit()
        return {"message": "Sensor data added successfully"}
    finally:
        cursor.close()
        conn.close()

@app.get("/dashboard/")
async def get_dashboard_data(token: str = Depends(oauth2_scheme)):
    user = get_current_user(token)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM sensor_data WHERE device_id IN (SELECT id FROM devices WHERE user_id = %s)", (user["id"],))
        sensor_data = cursor.fetchall()
        
        cursor.execute("SELECT * FROM wardrobe WHERE user_id = %s", (user["id"],))
        wardrobe_items = cursor.fetchall()
        
        return {"sensor_data": sensor_data, "wardrobe_items": wardrobe_items}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/sensor-data/")
async def add_sensor_data(data: dict):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO sensor_data (device_id, timestamp, temperature, humidity)
        VALUES (%s, %s, %s, %s)
        """, (
            data["device_id"],
            data["timestamp"],
            data["temperature"],
            data["humidity"]
        ))
        conn.commit()
        return {"message": "Sensor data added successfully"}
    except Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()