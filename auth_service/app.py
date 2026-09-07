import os
import re
from datetime import timedelta

from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///auth.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv(
    "JWT_SECRET_KEY", "development-secret-change-me-32-chars-long"
)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)

db = SQLAlchemy(app)
jwt = JWTManager(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    forename = db.Column(db.String(256), nullable=False)
    surname = db.Column(db.String(256), nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="EMPLOYEE")


def error(message, status_code=400):
    return jsonify(message=message), status_code


def valid_email(email):
    return isinstance(email, str) and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)


@jwt.unauthorized_loader
def missing_authorization_header(_reason):
    return jsonify(msg="Missing Authorization Header"), 401


@jwt.invalid_token_loader
def invalid_token(_reason):
    return jsonify(msg="Invalid token"), 401


@app.post("/register")
def register():
    data = request.get_json(silent=True) or {}

    for field in ("forename", "surname", "email", "password"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            return error(f"Field {field} is missing.")

    if not valid_email(data["email"]):
        return error("Invalid email.")
    if len(data["password"]) < 8:
        return error("Invalid password.")
    if len(data["forename"]) > 256 or len(data["surname"]) > 256:
        return error("Invalid user data.")
    if len(data["email"]) > 256 or len(data["password"]) > 256:
        return error("Invalid user data.")
    if User.query.filter_by(email=data["email"]).first() is not None:
        return error("Email already exists.")

    user = User(
        forename=data["forename"],
        surname=data["surname"],
        email=data["email"],
        password_hash=generate_password_hash(data["password"]),
        role="EMPLOYEE",
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("Email already exists.")

    return "", 200


@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}

    for field in ("email", "password"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            return error(f"Field {field} is missing.")
    if not valid_email(data["email"]):
        return error("Invalid email.")

    user = User.query.filter_by(email=data["email"]).first()
    if user is None or not check_password_hash(user.password_hash, data["password"]):
        return error("Invalid credentials.")

    token = create_access_token(
        identity=user.email,
        additional_claims={
            "forename": user.forename,
            "surname": user.surname,
            "role": user.role,
        },
    )
    return jsonify(accessToken=token), 200


@app.post("/delete")
@jwt_required()
def delete():
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()
    if user is None:
        return error("Unknown user.")

    db.session.delete(user)
    db.session.commit()
    return "", 200


def initialize_database():
    with app.app_context():
        db.create_all()
        if User.query.filter_by(email="onlymoney@gmail.com").first() is None:
            director = User(
                forename="Scrooge",
                surname="McDuck",
                email="onlymoney@gmail.com",
                password_hash=generate_password_hash("evenmoremoney"),
                role="DIRECTOR",
            )
            db.session.add(director)
            db.session.commit()


initialize_database()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)