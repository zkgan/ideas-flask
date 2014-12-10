import json
from bson import json_util
from bson.objectid import ObjectId
from flask import Flask, request
from mongokit import Document
from flask.ext.pymongo import PyMongo
import datetime
from simserver import SessionServer
from gensim import utils
import itertools
from pymongo import MongoClient

sim_server = SessionServer('./tmp/idea_match_server')
client = MongoClient('localhost', 3001)
db = client.meteor
cursor = db.ideas.find({})
corpus = [{'id': idea['_id'], 'tokens': utils.simple_preprocess(idea['text'])} for idea in cursor]
utils.upload_chunked(sim_server, corpus, chunksize=1000)
sim_server.train(corpus, method='lsi')
sim_server.index(corpus)

app = Flask(__name__)
app.config['MONGO_HOST'] = 'localhost'
app.config['MONGO_PORT'] = 3001
app.config['MONGO_DBNAME'] = 'meteor'
mongo = PyMongo(app)


class Idea(Document):
    structure = {
        'text':unicode,
        'parent_id': unicode,
        'date_created': datetime.datetime,
        'status': int, # open, pending, rejected, filled
        'suggested_relations': [],
        'relations': {},
    }
    required_fields = ['text', 'parent_id', 'date_created', 'status']
    default_values = {'text': u'', 'parent_id': u'', 'date_created': datetime.datetime.utcnow, 'status': 0}

class Relation(Document):
    structure = {
#        'targetIdea': unicode,
        'weight': float,
#        'manmade': bool,
        'confirms': int,
        'denies': int,
        'reviewed': bool,
    }
#    required_fields = ['targetIdea', 'weight']
    default_values = {'confirms': 0, 'denies': 0, 'reviewed': False}

@app.route("/")
def init_sim_server():
    return ''

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
    idea_id = mongo.db.ideas.insert(entry)

    return text #'Done'

@app.route("/delete_idea") #args: idea_id
def delete_idea():
    idea_id = request.args.get("idea_id")
    if idea_id == None:
        return "Must specify idea_id to delete"
    mongo.db.ideas.find_and_modify(
        query = {"_id": idea_id},
        remove = True
    )
    return "Object deleted."
    
@app.route("/read_ideas")
def read_ideas():
    idea_id = request.args.get("idea_id")
    text = request.args.get("text")
    print idea_id
    if idea_id:
        cursor = mongo.db.ideas.find({"_id": idea_id})
    else:
        if text == None:
            cursor = mongo.db.ideas.find({})
        else:
            cursor = mongo.db.ideas.find({"text": text})
    return multipleToJson(cursor)

def compute_relations(idea_id): # Computes relations for idea specified by idea_id
    # Now we have a working sim_server, find similar ideas!
    matches = sim_server.find_similar(idea_id, min_score = 0.09)
    matched_ideas = []
    for match in matches:
        match_id = match[0]
        match_score = match[1]
        if match_id != idea_id:
            relation = Relation()
            relation['weight'] = match_score
            matched_ideas.append((match_id, relation))
    #result = itertools.chain.from_iterable(matched_ideas)
    #return multipleToJson(result)
    return matched_ideas

@app.route("/add_suggested_relations") # Computes and adds computed relations to idea. args: idea_id
def add_suggested_relations():
    idea_id = request.args.get("idea_id")
    if idea_id == None:
        return "Must provide idea id to find relations!"
    if idea_id not in sim_server.keys():
        index_new_idea(idea_id)
    idea = _add_suggested_relations(idea_id)
    return toJson(idea)

@app.route("/add_all_suggested_relations") # Computes and adds computed relations to all ideas.
def add_all_suggested_relations():
    all_ideas = mongo.db.ideas.find({})
    for idea in all_ideas:
        idea_id = idea["_id"]
        if idea_id not in sim_server.keys():
            index_new_idea(idea_id)
        _add_suggested_relations(idea_id)
    return multipleToJson(all_ideas)

def index_new_idea(idea_id):
    idea = mongo.db.ideas.find_one({"_id": idea_id})
    corpus = [{'id': idea['_id'], 'tokens': utils.simple_preprocess(idea['text'])}]
    sim_server.index(corpus)

def _add_suggested_relations(idea_id):
    matched_ideas = compute_relations(idea_id)
    idea = mongo.db.ideas.find_one({"_id": idea_id})

    if "relations" in idea:
        relations = idea["relations"]
    else:
        relations = {}
    idea_is_updated = False
    for match_id, relation in matched_ideas:
        if match_id not in relations:
            relations[match_id] = relation
            idea_is_updated = True
#    idea_is_updated = True
#    relations = {}
    if idea_is_updated:
        idea = mongo.db.ideas.find_and_modify(
            query = {"_id": idea_id},
            update = {"$set": {"relations": relations}},
            new = True
        )
    return idea

@app.route("/read_relations")
def read_relations():
    relation_id = request.args.get("relation_id")
    if relation_id == None:
        cursor = mongo.db.relations.find({})
    else:
        cursor = mongo.db.relations.find({"_id": ObjectId(relation_id)})
    resp = Response(response=multipleToJson(cursor),
                    status=200,
                    mimetype="application/json")
    return resp

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

@app.route("/clear_all_relations")
def clear_all_relations():
    ideas = mongo.db.ideas.find({})
    for idea in all_ideas:
        idea_id = idea["_id"]
        relations = {}
        idea = mongo.db.ideas.find_and_modify(
            query = {"_id": idea_id},
            update = {"$set": {"relations": {}}},
            new = True
        )
    return multipleToJson(ideas)


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
