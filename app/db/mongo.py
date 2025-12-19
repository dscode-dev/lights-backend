from __future__ import annotations

from pymongo import MongoClient
from pymongo.database import Database


class Mongo:
    def __init__(self, client: MongoClient, db: Database):
        self.client = client
        self.db = db
