from vkapi8 import *
from .creds import login, password, client


api = None


def test_init(scope='groups'):
    global api
    api = VKApi(login, password, client, scope, debug=True)


def test_get_groups_data():
    for chunk in api.get_groups_by_id(list(range(1, 2000))):
        print(chunk)
