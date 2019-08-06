import random
import uuid

import factory

from core import models
from hashlib import sha1
from factory.django import DjangoModelFactory
from codecov_auth.tests.factories import OwnerFactory


class RepositoryFactory(DjangoModelFactory):
    class Meta:
        model = models.Repository

    private = True
    name = 'example-python'
    author = factory.SubFactory(OwnerFactory)
    language = factory.Faker('word')
    fork = None
    branch = 'master'
    upload_token = uuid.uuid4()


class CommitFactory(DjangoModelFactory):
    class Meta:
        model = models.Commit

    commitid = factory.LazyAttribute(lambda o: sha1(o.message.encode('utf-8')).hexdigest())
    message = factory.Faker('sentence', nb_words=7)
    ci_passed = True
    pullid = 1
    author = factory.SubFactory(OwnerFactory)
    repository = factory.SubFactory(RepositoryFactory)
    branch = 'master'
    totals = {
        'C': 0,
        'M': 0,
        'N': 0,
        'b': 0,
        'c': '85.00000',
        'd': 0,
        'diff': [1, 2, 1, 1, 0, '50.00000', 0, 0, 0, 0, 0, 0, 0],
        'f': 3,
        'h': 17,
        'm': 3,
        'n': 20,
        'p': 0,
        's': 1
    }
    report = {
        'files': {
            'awesome/__init__.py': [
                2,
                [0, 10, 8, 2, 0, '80.00000', 0, 0, 0, 0, 0, 0, 0],
                [[0, 10, 8, 2, 0, '80.00000', 0, 0, 0, 0, 0, 0, 0]],
                [0, 2, 1, 1, 0, '50.00000', 0, 0, 0, 0, 0, 0, 0]
            ],
            'tests/__init__.py': [
                0,
                [0, 3, 2, 1, 0, '66.66667', 0, 0, 0, 0, 0, 0, 0],
                [[0, 3, 2, 1, 0, '66.66667', 0, 0, 0, 0, 0, 0, 0]],
                None
            ],
            'tests/test_sample.py': [
                1,
                [0, 7, 7, 0, 0, '100', 0, 0, 0, 0, 0, 0, 0],
                [[0, 7, 7, 0, 0, '100', 0, 0, 0, 0, 0, 0, 0]],
                None
            ]
        },
        'sessions': {
            '0': {
                'N': None,
                'a': 'v4/raw/2019-01-10/4434BC2A2EC4FCA57F77B473D83F928C/abf6d4df662c47e32460020ab14abf9303581429/9ccc55a1-8b41-4bb1-a946-ee7a33a7fb56.txt',
                'c': None,
                'd': 1547084427,
                'e': None,
                'f': ['unittests'],
                'j': None,
                'n': None,
                'p': None,
                't': [3, 20, 17, 3, 0, '85.00000', 0, 0, 0, 0, 0, 0, 0],
                '': None
            },
            '1': {
                'N': None,
                'a': 'v4/raw/2019-01-10/4434BC2A2EC4FCA57F77B473D83F928C/abf6d4df662c47e32460020ab14abf9303581429/9ccc55a1-8b41-4bb1-a946-ee7a33a7fb56.txt',
                'c': None,
                'd': 1547084427,
                'e': None,
                'f': ['integrations'],
                'j': None,
                'n': None,
                'p': None,
                't': [3, 20, 17, 3, 0, '85.00000', 0, 0, 0, 0, 0, 0, 0],
                '': None
            }
        }
    }
    parent_commit_id = factory.LazyAttribute(lambda o: sha1((o.message + "parent").encode('utf-8')).hexdigest())
    state = 'complete'


class PullFactory(DjangoModelFactory):
    class Meta:
        model = models.Pull

    issueid = random.randint(1, 1000)
    commentid = factory.LazyAttribute(lambda o: sha1(o.title.encode('utf-8')).hexdigest())
    flare = {
            "name": "",
            "color": "#e05d44",
            "lines": 14,
            "_class": None,
            "children": [{
                    "name": "tests.py",
                    "color": "#baaf1b",
                    "lines": 7,
                    "_class": None,
                    "coverage": "85.71429"
            }]
    }
    diff = [
        2,
        3,
        0,
        3,
        0,
        "0",
        0,
        0,
        0,
        0,
        0,
        0,
        0
    ]
    title = factory.Faker('sentence', nb_words=7)
    base = factory.SubFactory(CommitFactory)
    head = factory.SubFactory(CommitFactory)
    compared_to = factory.SubFactory(CommitFactory)


class BranchFactory(DjangoModelFactory):
    class Meta:
        model = models.Branch

    name = factory.Faker('sentence', nb_words=1)
    head = factory.SubFactory(CommitFactory)


class VersionFactory(DjangoModelFactory):
    class Meta:
        model = models.Version
