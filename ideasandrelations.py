import json
from bson import json_util
from bson.objectid import ObjectId
from flask import Flask, request
from mongokit import Document
from flask.ext.pymongo import PyMongo
import datetime

app = Flask(__name__)
app.config['MONGO_HOST'] = 'localhost'
#app.config['MONGO_PORT'] = 3001
#app.config['MONGO_DBNAME'] = 'meteor'
mongo = PyMongo(app)

class Idea(Document):
    structure = {
        'text':unicode,
        'parent_id': unicode,
        'date_created': datetime.datetime,
        'status': int, # open, pending, rejected, filled
        'suggested_relations': [],
        'related_ideas': {},
    }
    required_fields = ['text', 'parent_id', 'date_created', 'status']
    default_values = {'text': u'', 'parent_id': u'', 'date_created': datetime.datetime.utcnow, 'status': 0}

class Relation(Document):
    structure = {
        #'_id': unicode,
        'text': unicode,
        'source_id': unicode,
        'target_id': unicode,
        'weight': float,
        'manmade': bool,
        'confirms': int,
        'denies': int,
    }
    required_fields = ['text']
    default_values = {'confirms': 0, 'denies': 0}

@app.route("/")
def show_entries():
    return ' ,'.join(mongo.cx.database_names())
# create read update delete
@app.route("/create_idea")
def create_idea():
    text = request.args.get("text")
    parent_id = request.args.get("parent_id")
    status = request.args.get("status", 0)
    if text == None:
        return 'Must specify text to create an idea!'
    entry = Idea()
    entry['text'] = text
    entry['parent_id'] = parent_id
    entry['status'] = status
    ideas = mongo.db.ideas
    idea_id = ideas.insert(entry)

    return text #'Done'

@app.route("/delete_idea") #args: idea_id
def delete_idea():
    idea_id = request.args.get("idea_id")
    if idea_id == None:
        return "Must specify idea_id to delete"
    mongo.db.relations.find_and_modify(
        query = {"_id": ObjectId(idea_id)},
        remove = True
    )
    return "Object deleted."
    

@app.route("/read_ideas")
def read_ideas():
    text = request.args.get("text")
    if text == None:
        cursor = mongo.db.ideas.find({})
    else:
        cursor = mongo.db.ideas.find({"text": text})
    return multipleToJson(cursor)

@app.route("/add_suggested_relation") #args: idea_id, relation_id
def add_suggested_relation():
    idea_id = request.args.get("idea_id")
    relation_id = request.args.get("relation_id")
    idea = mongo.db.ideas.find_and_modify(
        query = {"_id": ObjectId(idea_id)},
        update = {"$addToSet": {"suggested_relations": relation_id}},
        new = True
    )
    return toJson(idea)


@app.route("/read_relations")
def read_relations():
    relation_id = request.args.get("relation_id")
    if relation_id == None:
        cursor = mongo.db.relations.find({})
    else:
        cursor = mongo.db.relations.find({"_id": ObjectId(relation_id)})
    return multipleToJson(cursor)

@app.route("/create_relation") #arguments: text, strength, source, target, manmade
def create_relation():
    text = request.args.get("text")
    strength = request.args.get("strength", 0)
    source_id = request.args.get("source_id")
    target_id = request.args.get("target_id")

    if text == None:
        return 'Cannot insert relation with no text'
    entry = Relation()
    entry['text'] = text
    entry['strength'] = strength
    entry['source_id'] = source_id
    entry['target_id'] = target_id
    entry['manmade'] = True

    relations = mongo.db.relations
    relation_id = relations.insert(entry)

    return text #'Done'

@app.route("/get_suggested_relations") #arguments: idea_id
def get_suggested_relations():
    idea_id = request.args.get("idea_id")
    idea = mongo.db.ideas.find_one({"_id": ObjectId(idea_id)})
    suggested_relations = idea['suggested_relations']
    print suggested_relations
    return toJson(suggested_relations)

def auto_suggest_relations(): #argument: text
    suggested_relation = mongo.db.relations.find_one()
    return suggested_relation

@app.route("/relation_feedback")
def relation_feedback(): #arguments: relation_id, confirm, deny, user
    relation_id = request.args.get("relation_id")
    if not relation_id:
        return "No relation id given."
    confirm = request.args.get("confirm", False)
    deny = request.args.get("deny", False)
    user = request.args.get("user")

    confirm_increment = 0
    deny_increment = 0
    if confirm:
        confirm_increment = 1
    if deny:
        deny_increment = 1

    relation = mongo.db.relations.find_and_modify(
        query = {"_id": ObjectId(relation_id)},
        update = {"$inc": {"confirms": confirm_increment, "denies": deny_increment}},
        new = True
    )
    return toJson(relation)

def toJson(data):
    """Convert Mongo object(s) to JSON"""
    return json.dumps(data, default=json_util.default)

def multipleToJson(cursor):
    json_results = []
    for result in cursor:
      json_results.append(result)
    return toJson(json_results)


if __name__ == "__main__":
    app.run (debug=True)
