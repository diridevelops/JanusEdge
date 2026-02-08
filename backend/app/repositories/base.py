"""Base repository with common CRUD operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.extensions import mongo


class BaseRepository:
    """
    Base repository providing common MongoDB CRUD operations.

    Subclasses must set `collection_name` class attribute.
    """

    collection_name: str = ""

    @property
    def collection(self):
        """Return the MongoDB collection for this repository."""
        return mongo.db[self.collection_name]

    def find_by_id(self, doc_id: str) -> Optional[Dict]:
        """
        Find a document by its ObjectId.

        Parameters:
            doc_id: String representation of the ObjectId.

        Returns:
            The document dict or None.
        """
        return self.collection.find_one({"_id": ObjectId(doc_id)})

    def find_one(self, query: Dict) -> Optional[Dict]:
        """
        Find a single document matching the query.

        Parameters:
            query: MongoDB query dict.

        Returns:
            The document dict or None.
        """
        return self.collection.find_one(query)

    def find_many(
        self,
        query: Dict,
        sort: List = None,
        skip: int = 0,
        limit: int = 0,
        projection: Dict = None,
    ) -> List[Dict]:
        """
        Find multiple documents matching the query.

        Parameters:
            query: MongoDB query dict.
            sort: List of (field, direction) tuples.
            skip: Number of results to skip.
            limit: Max number of results (0 = no limit).
            projection: Fields to include/exclude.

        Returns:
            List of document dicts.
        """
        cursor = self.collection.find(query, projection)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def count(self, query: Dict) -> int:
        """
        Count documents matching the query.

        Parameters:
            query: MongoDB query dict.

        Returns:
            Count of matching documents.
        """
        return self.collection.count_documents(query)

    def insert_one(self, document: Dict) -> str:
        """
        Insert a single document.

        Parameters:
            document: The document to insert.

        Returns:
            String representation of the inserted ObjectId.
        """
        result = self.collection.insert_one(document)
        return str(result.inserted_id)

    def insert_many(self, documents: List[Dict]) -> List[str]:
        """
        Insert multiple documents.

        Parameters:
            documents: List of documents to insert.

        Returns:
            List of inserted ObjectId strings.
        """
        if not documents:
            return []
        result = self.collection.insert_many(documents)
        return [str(oid) for oid in result.inserted_ids]

    def update_one(
        self, doc_id: str, update: Dict
    ) -> bool:
        """
        Update a single document by ObjectId.

        Parameters:
            doc_id: String representation of the ObjectId.
            update: MongoDB update dict (e.g. {"$set": {...}}).

        Returns:
            True if a document was modified.
        """
        result = self.collection.update_one(
            {"_id": ObjectId(doc_id)}, update
        )
        return result.modified_count > 0

    def delete_one(self, doc_id: str) -> bool:
        """
        Delete a single document by ObjectId.

        Parameters:
            doc_id: String representation of the ObjectId.

        Returns:
            True if a document was deleted.
        """
        result = self.collection.delete_one(
            {"_id": ObjectId(doc_id)}
        )
        return result.deleted_count > 0

    def delete_many(self, query: Dict) -> int:
        """
        Delete multiple documents matching the query.

        Parameters:
            query: MongoDB query dict.

        Returns:
            Number of deleted documents.
        """
        result = self.collection.delete_many(query)
        return result.deleted_count

    def aggregate(self, pipeline: List[Dict]) -> List[Dict]:
        """
        Run an aggregation pipeline.

        Parameters:
            pipeline: MongoDB aggregation pipeline.

        Returns:
            List of result documents.
        """
        return list(self.collection.aggregate(pipeline))

    @staticmethod
    def to_object_id(id_string: str) -> ObjectId:
        """
        Convert a string to ObjectId.

        Parameters:
            id_string: String to convert.

        Returns:
            ObjectId instance.
        """
        return ObjectId(id_string)

    @staticmethod
    def _serialize_value(value):
        """Serialize a single value for JSON output."""
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.isoformat() + "+00:00"
            return value.isoformat()
        return value

    @staticmethod
    def serialize_doc(doc: Dict) -> Dict:
        """
        Serialize a MongoDB document for JSON response.

        Converts ObjectId fields to strings.

        Parameters:
            doc: MongoDB document dict.

        Returns:
            Serialized dict with string IDs.
        """
        if doc is None:
            return None
        result = {}
        for key, value in doc.items():
            out_key = "id" if key == "_id" else key
            if isinstance(value, ObjectId):
                result[out_key] = str(value)
            elif isinstance(value, datetime):
                if value.tzinfo is None:
                    result[out_key] = value.isoformat() + "+00:00"
                else:
                    result[out_key] = value.isoformat()
            elif isinstance(value, list):
                result[out_key] = [
                    BaseRepository._serialize_value(v)
                    for v in value
                ]
            else:
                result[out_key] = value
        return result
