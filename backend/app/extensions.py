"""Flask extension instances for TradeLogs."""

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_pymongo import PyMongo

mongo = PyMongo()
jwt = JWTManager()
cors = CORS()
