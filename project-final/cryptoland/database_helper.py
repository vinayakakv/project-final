import rapidjson

from pymongo import MongoClient


class DatabaseHelper:
    def __init__(self, url):
        self.client = MongoClient(url)

    def get_user_details(self, public_key):
        try:
            db = self.client.bigchain
            result = db.assets.find_one({
                'data.key': public_key,
                'data.type': 'REGISTER_USER',
                'data.user_type': 'USER'
            }, {"_id": 0, 'data.name': 1})
            if not result:
                raise Exception("Can not find user. Maybe key is wrong or key is not a type of USER")
            return {"success": True, "data": result['data']}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_surveyor_details(self, public_key):
        try:
            db = self.client.bigchain
            pipeline = [
                {
                    '$match': {
                        'operation': 'CREATE'
                    }
                }, {
                    '$project': {
                        '_id': 0,
                        'id': 1,
                        'inputs': 1,
                        'outputs': 1
                    }
                }, {
                    '$lookup': {
                        'from': 'assets',
                        'localField': 'id',
                        'foreignField': 'id',
                        'as': 'asset'
                    }
                }, {
                    '$match': {
                        'asset.data.type': 'SURVEY',
                        'inputs.owners_before': public_key
                    }
                }, {
                    '$unwind': {
                        'path': '$outputs',
                        'preserveNullAndEmptyArrays': False
                    }
                }, {
                    '$group': {
                        '_id': None,
                        'count': {
                            '$sum': 1
                        },
                        'totalAcre': {
                            '$sum': {
                                '$divide': [
                                    {
                                        '$toDouble': '$outputs.amount'
                                    }, 40468.6
                                ]
                            }
                        }
                    }
                }
            ]
            result = list(db.transactions.aggregate(pipeline))
            if not result:
                raise Exception(
                    "Surveyor details can not be found. Maybe key is wrong or key is not a type of SURVEYOR")
            result = result[0]
            del result['_id']
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_survey(self, survey_number):
        db = self.client.bigchain
        return db.assets.find_one({"data.type": "SURVEY", "data.surveyNumber": survey_number}, {"_id": 0})

    def get_land_transactions(self, transaction_ids: list):
        try:
            db = self.client.bigchain
            pipeline = [
                {
                    '$match': {
                        'id': {
                            '$in': transaction_ids
                        }
                    }
                }, {
                    '$lookup': {
                        'from': 'metadata',
                        'localField': 'id',
                        'foreignField': 'id',
                        'as': 'metadata'
                    }
                }, {
                    '$lookup': {
                        'from': 'assets',
                        'localField': 'asset.id',
                        'foreignField': 'id',
                        'as': 'asset'
                    }
                }, {
                    '$lookup': {
                        'from': 'assets',
                        'localField': 'id',
                        'foreignField': 'id',
                        'as': 'asset_create'
                    }
                }, {
                    '$unwind': {
                        'path': '$asset',
                        'preserveNullAndEmptyArrays': True
                    }
                }, {
                    '$unwind': {
                        'path': '$asset_create',
                        'preserveNullAndEmptyArrays': True
                    }
                }, {
                    '$unwind': {
                        'path': '$metadata',
                        'preserveNullAndEmptyArrays': True
                    }
                }, {
                    '$project': {
                        'asset': [
                            '$asset_create.data', '$asset.data'
                        ],
                        'metadata': '$metadata.metadata.divisions',
                        'txid': '$id',
                        'outputs': '$outputs.public_keys'
                    }
                }, {
                    '$unwind': {
                        'path': '$asset',
                        'preserveNullAndEmptyArrays': False
                    }
                }, {
                    '$match': {
                        'asset': {
                            '$ne': None
                        },
                        'asset.type': 'SURVEY'
                    }
                }
            ]
            result = list(db.transactions.aggregate(pipeline))
            return result
        except:
            return []

    def get_subpart_number(self, asset_id):
        try:
            db = self.client.bigchain
            pipeline = [
                {
                    '$match': {
                        'metadata.asset_id': asset_id
                    }
                }, {
                    '$group': {
                        '_id': 'stats',
                        'subpart_number': {
                            '$max': {
                                '$max': [
                                    '$metadata.divisions.from_data.subpart_number',
                                    '$metadata.divisions.to_data.subpart_number'
                                ]
                            }
                        }
                    }
                }
            ]
            result = list(db.metadata.aggregate(pipeline))
            subpart_number = result[0]['subpart_number'] if result else 0
            subpart_number = subpart_number if subpart_number else 0
            return subpart_number + 1
        except Exception as e:
            raise e

    def get_asset_history(self, survey_number):
        try:
            db = self.client.bigchain
            asset = db.assets.find_one({"data.surveyNumber": survey_number})
            if not asset:
                raise Exception("Survey number not found")
            asset_id = asset['id']
            pipeline = [
                {
                    '$match': {
                        '$or': [
                            {
                                'operation': 'CREATE',
                                'id': asset_id
                            }, {
                                'operation': 'TRANSFER',
                                'asset.id': asset_id
                            }
                        ]
                    }
                }, {
                    '$lookup': {
                        'from': 'metadata',
                        'localField': 'id',
                        'foreignField': 'id',
                        'as': 'metadata'
                    }
                }, {
                    '$unwind': {
                        'path': '$metadata',
                        'preserveNullAndEmptyArrays': False
                    }
                }, {
                    '$replaceRoot': {
                        'newRoot': '$metadata'
                    }
                }
            ]
            nodes = []
            edges = []
            mapping = self.get_user_mapping()
            for i, tx in enumerate(db.transactions.aggregate(pipeline)):
                (from_data, to_data) = [tx['metadata']['divisions']['from_data'],
                                        tx['metadata']['divisions']['to_data']]
                parent_node = None
                for node in nodes[::-1]:
                    if node['subpart_number'] == from_data['subpart_number'] and \
                            node['public_key'] == from_data['public_key'] and \
                            node['area'] >= from_data['area']:
                        parent_node = node
                        break
                parent_id = parent_node['id'] if parent_node else None
                if from_data['area'] > 0:
                    left_node = {
                        "id": "{}:{}".format(i, 1),
                        "boundaries": rapidjson.loads(from_data['boundaries']),
                        "area": from_data['area'],
                        "public_key": from_data['public_key'],
                        "user_name": mapping[from_data['public_key']],
                        "subpart_number": from_data['subpart_number']
                    }
                    subpart_number = left_node['subpart_number']
                    subpart_number = "/" + str(subpart_number) if subpart_number != 0 else ""
                    left_node['label'] = "Survey:{}{}\nOwner:{}\nArea:{}".format(
                        survey_number,
                        subpart_number,
                        left_node['user_name'],
                        left_node['area']
                    )
                    nodes.append(left_node)
                    if parent_id:
                        edges.append({'from': parent_id, 'to': left_node['id']})
                right_node = {
                    "id": "{}:{}".format(i, 2),
                    "boundaries": rapidjson.loads(to_data['boundaries']),
                    "area": to_data['area'],
                    "public_key": to_data['public_key'],
                    "user_name": mapping[to_data['public_key']],
                    "subpart_number": to_data['subpart_number']
                }
                subpart_number = right_node['subpart_number']
                subpart_number = "/" + str(subpart_number) if subpart_number != 0 else ""
                right_node['label'] = "Survey:{}{}\nOwner:{}\nArea:{}".format(
                    survey_number,
                    subpart_number,
                    right_node['user_name'],
                    right_node['area']
                )
                nodes.append(right_node)
                if parent_id:
                    edges.append({'from': parent_id, 'to': right_node['id']})
            return {"success": True, "data": {"nodes": nodes, "edges": edges}}
        except Exception as e:
            return {"success": False, "message": repr(e)}

    def get_user_asset(self, public_key):
        db = self.client.bigchain
        return db.assets.find_one({
            "data.type": {"$in": ["REGISTER_USER", "CREATE_USER"]},
            "data.key": public_key
        })

    def retrieve_assets(self, asset_type):
        db = self.client.bigchain
        return list(db.assets.find({"data.type": asset_type}, {"_id": 0}))

    def find_asset(self, key, value):
        db = self.client.bigchain
        return list(db.assets.find({key: value}, {"_id": 0}))

    def get_transfer_requests(self):
        try:
            db = self.client.bigchain
            pipeline = [
                {
                    '$match': {
                        'data.type': 'TRANSFER_REQUEST'
                    }
                }, {
                    '$lookup': {
                        'from': 'assets',
                        'localField': 'data.asset',
                        'foreignField': 'id',
                        'as': 'asset'
                    }
                }, {
                    '$unwind': {
                        'path': '$asset',
                        'preserveNullAndEmptyArrays': False
                    }
                }
            ]
            results = list(db.assets.aggregate(pipeline))
            return results
        except Exception:
            return []

    def get_user_mapping(self):
        try:
            db = self.client.bigchain
            pipeline = [
                {
                    '$match': {
                        'data.type': 'REGISTER_USER'
                    }
                }, {
                    '$group': {
                        '_id': 'user_data',
                        'mapping': {
                            '$push': {
                                'name': '$data.name',
                                'key': '$data.key'
                            }
                        }
                    }
                }
            ]
            result = list(db.assets.aggregate(pipeline))
            if len(result) == 0:
                raise Exception()
            result = result[0]
            mapping = {}
            for pair in result['mapping']:
                mapping[pair['key']] = pair['name']
            return mapping
        except:
            return {}
