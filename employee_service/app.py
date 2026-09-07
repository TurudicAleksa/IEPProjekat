import json
import os
import re
from datetime import datetime, timedelta
from uuid import uuid4

from bson.json_util import dumps
from bson.objectid import ObjectId
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, get_jwt_identity, jwt_required
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


def parse_iso_date(date_str):
    """Parse ISO 8601 date string."""
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


@app.post("/search")
@jwt_required()
def search():
    email = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    try:
        db = get_mongo()
    except ServerSelectionTimeoutError:
        return error("Database connection failed", 500)

    query = {}

    if "name" in data and isinstance(data["name"], str) and data["name"].strip():
        if len(data["name"]) > 256:
            return error("Invalid search criteria", 400)
        query["name"] = {"$regex": re.escape(data["name"]), "$options": "i"}

    if "category" in data and isinstance(data["category"], str) and data["category"].strip():
        if len(data["category"]) > 256:
            return error("Invalid search criteria", 400)
        query["categories"] = data["category"]

    if "buying_date" in data and isinstance(data["buying_date"], str):
        buying_date = parse_iso_date(data["buying_date"])
        if buying_date:
            query["buying_date"] = {"$gte": buying_date}

    if "selling_date" in data and isinstance(data["selling_date"], str):
        selling_date = parse_iso_date(data["selling_date"])
        if selling_date:
            query["$and"] = [
                {"selling_date": {"$lte": selling_date}},
                {"selling_date": {"$exists": True}},
            ]

    if "info_filters" in data and isinstance(data["info_filters"], list):
        allowed_operators = {
            "$eq", "$ne", "$gt", "$gte", "$lt", "$lte",
            "$in", "$nin", "$exists", "$type", "$regex"
        }
        for info_filter in data["info_filters"]:
            if not isinstance(info_filter, dict):
                continue
            field = info_filter.get("field")
            operator = info_filter.get("operator")
            value = info_filter.get("value")

            if not field or not operator or operator not in allowed_operators:
                continue

            query_key = f"info.{field}"
            if query_key not in query:
                query[query_key] = {}
            query[query_key][operator] = value

    assets = list(db.assets.find(query))
    result = []
    for asset in assets:
        result.append({
            "id": str(asset.get("_id")),
            "name": asset.get("name"),
            "categories": asset.get("categories", []),
            "buying_date": asset.get("buying_date").isoformat() if asset.get("buying_date") else None,
            "buying_price": asset.get("buying_price"),
            "selling_date": asset.get("selling_date").isoformat() if asset.get("selling_date") else None,
            "selling_price": asset.get("selling_price"),
            "info": asset.get("info", {}),
        })

    return jsonify(assets=result), 200


@app.post("/create_buy_order")
@jwt_required()
def create_buy_order():
    email = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    for field in ("name", "categories", "buying_price", "info"):
        if field not in data:
            return error(f"Field {field} is missing.")

    if not isinstance(data["name"], str) or not data["name"].strip():
        return error("Field name is missing.")
    if len(data["name"]) > 256:
        return error("Field name is missing.")

    if not isinstance(data["categories"], list) or len(data["categories"]) == 0:
        return error("Categories list is empty.")
    for cat in data["categories"]:
        if not isinstance(cat, str) or len(cat) > 256:
            return error("Categories list is empty.")

    if not isinstance(data["buying_price"], (int, float)) or data["buying_price"] <= 0:
        return error("Invalid buying price.")

    if not isinstance(data["info"], dict):
        return error("Field info is missing.")

    try:
        r = get_redis()
    except Exception:
        return error("Redis connection failed", 500)

    order = {
        "uuid": str(uuid4()),
        "order_type": "BUY",
        "name": data["name"],
        "categories": data["categories"],
        "buying_price": data["buying_price"],
        "info": data["info"],
    }

    try:
        r.set(f"order:{order['uuid']}", json.dumps(order))
    except Exception:
        return error("Failed to create order", 500)

    return "", 200


@app.post("/create_sell_order")
@jwt_required()
def create_sell_order():
    email = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    for field in ("id", "selling_price"):
        if field not in data:
            return error(f"Field {field} is missing.")

    asset_id = data.get("id")
    if not isinstance(asset_id, str) or not asset_id.strip():
        return error("Field id is missing.")

    if not ObjectId.is_valid(asset_id):
        return error("Invalid id.")

    try:
        db = get_mongo()
    except ServerSelectionTimeoutError:
        return error("Database connection failed", 500)

    asset = db.assets.find_one({"_id": ObjectId(asset_id)})
    if asset is None:
        return error("Invalid id.")

    if not isinstance(data["selling_price"], (int, float)) or data["selling_price"] <= 0:
        return error("Invalid selling price.")

    try:
        r = get_redis()
    except Exception:
        return error("Redis connection failed", 500)

    order = {
        "uuid": str(uuid4()),
        "order_type": "SELL",
        "id": asset_id,
        "selling_price": data["selling_price"],
    }

    try:
        r.set(f"order:{order['uuid']}", json.dumps(order))
    except Exception:
        return error("Failed to create order", 500)

    return "", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")), debug=True)
