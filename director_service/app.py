import json
import os
from datetime import datetime
from uuid import UUID

from bson.objectid import ObjectId
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, get_jwt_identity, get_jwt, jwt_required
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import redis


app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv(
    "JWT_SECRET_KEY", "development-secret-change-me-32-chars-long"
)

jwt = JWTManager(app)


def get_mongo():
    """Get MongoDB client."""
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    return client[os.getenv("MONGO_DB", "investment_fund")]


def get_redis():
    """Get Redis client."""
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    return redis.Redis(host=redis_host, port=redis_port, decode_responses=True)


def error(message, status_code=400):
    return jsonify(message=message), status_code


@jwt.unauthorized_loader
def missing_authorization_header(_reason):
    return jsonify(msg="Missing Authorization Header"), 401


@jwt.invalid_token_loader
def invalid_token(_reason):
    return jsonify(msg="Invalid token"), 401


def is_director(claims):
    """Check if user is a director."""
    return claims.get("role") == "DIRECTOR"


@app.post("/pending_orders")
@jwt_required()
def pending_orders():
    claims = get_jwt()
    if not is_director(claims):
        return error("Unauthorized", 403)

    try:
        r = get_redis()
    except Exception:
        return error("Redis connection failed", 500)

    orders = []
    for key in r.keys("order:*"):
        order_data = r.get(key)
        if order_data:
            try:
                order = json.loads(order_data)
                orders.append(order)
            except json.JSONDecodeError:
                pass

    return jsonify(orders=orders), 200


@app.post("/decision")
@jwt_required()
def decision():
    claims = get_jwt()
    if not is_director(claims):
        return error("Unauthorized", 403)

    data = request.get_json(silent=True) or {}

    if "uuid" not in data:
        return error("Field uuid is missing.")
    if not isinstance(data["uuid"], str) or not data["uuid"].strip():
        return error("Field uuid is missing.")

    try:
        UUID(data["uuid"])
    except ValueError:
        return error("Invalid uuid.")

    if "approved" not in data:
        return error("Field approved is missing.")
    if not isinstance(data["approved"], bool):
        return error("Invalid decision.")

    try:
        r = get_redis()
        db = get_mongo()
    except Exception:
        return error("Connection failed", 500)

    order_key = f"order:{data['uuid']}"
    order_data = r.get(order_key)
    if not order_data:
        return error("Invalid uuid.")

    try:
        order = json.loads(order_data)
    except json.JSONDecodeError:
        return error("Invalid uuid.")

    if data["approved"]:
        if order["order_type"] == "BUY":
            asset = {
                "name": order["name"],
                "categories": order["categories"],
                "buying_price": order["buying_price"],
                "buying_date": datetime.utcnow(),
                "info": order["info"],
            }
            db.assets.insert_one(asset)
        elif order["order_type"] == "SELL":
            asset_id = order["id"]
            if ObjectId.is_valid(asset_id):
                db.assets.update_one(
                    {"_id": ObjectId(asset_id)},
                    {"$set": {
                        "selling_price": order["selling_price"],
                        "selling_date": datetime.utcnow(),
                    }}
                )

    r.delete(order_key)
    return "", 200


@app.get("/report")
@jwt_required()
def report():
    claims = get_jwt()
    if not is_director(claims):
        return error("Unauthorized", 403)

    try:
        db = get_mongo()
    except ServerSelectionTimeoutError:
        return error("Database connection failed", 500)

    pipeline = [
        {"$unwind": "$categories"},
        {
            "$group": {
                "_id": "$categories",
                "spent": {"$sum": "$buying_price"},
                "earned": {
                    "$sum": {
                        "$cond": [{"$ne": ["$selling_price", None]}, "$selling_price", 0]
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "category": "$_id",
                "spent": 1,
                "earned": 1,
            }
        },
        {
            "$sort": {
                "earned": -1,
                "spent": 1,
                "category": 1,
            }
        },
    ]

    try:
        stats = list(db.assets.aggregate(pipeline))
    except Exception:
        stats = []

    return jsonify(statistics=stats), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5002")), debug=True)
